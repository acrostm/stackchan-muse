// SPDX-License-Identifier: Apache-2.0
/* Route only Muse cloud TCP sockets through a user-owned LAN SOCKS5 proxy.
 * SOCKS resolves the original hostname; TLS still validates that hostname.
 * No TLS interception, certificate bypass, cloud credential forwarding or
 * host-wide proxy setting is involved. */
#include "sw_proxy.h"
#include "sw_proxy_core.h"
#include "esp_timer.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include "nvs.h"
#include "esp_wifi.h"
#include "muse_settings.h"
#include <errno.h>
#include <sys/select.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>

#define SLOTS 16
static SemaphoreHandle_t lock;
static sw_proxy_profiles_t profiles;
static sw_proxy_config_t pending;
static char pending_ssid[33];
static bool requested;
static EXT_RAM_BSS_ATTR char names[SLOTS][254], name_ssids[SLOTS][33];
extern int __real_lwip_getaddrinfo(const char *, const char *, const struct addrinfo *, struct addrinfo **);
extern int __real_lwip_connect(int, const struct sockaddr *, socklen_t);

static bool active_ssid(char out[33])
{
    wifi_ap_record_t ap;
    out[0] = 0;
    if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK) return false;
    memcpy(out, ap.ssid, 32); out[32] = 0;
    return out[0] != 0;
}
static void preferred_ssid(char out[33])
{
    char pass[65]; muse_settings_wifi(out, pass); memset(pass, 0, sizeof(pass));
}
void sw_proxy_get_for(const char *ssid, sw_proxy_config_t *out)
{
    memset(out, 0, sizeof(*out));
    if (!lock) return;
    xSemaphoreTake(lock, portMAX_DELAY);
    sw_proxy_profile_get(&profiles, ssid, out);
    xSemaphoreGive(lock);
}
void sw_proxy_snapshot(sw_proxy_profiles_t *out)
{
    xSemaphoreTake(lock, portMAX_DELAY); *out = profiles; xSemaphoreGive(lock);
}
void sw_proxy_get(sw_proxy_config_t *out)
{
    char ssid[33];
    if (!active_ssid(ssid)) { memset(out, 0, sizeof(*out)); return; }
    sw_proxy_get_for(ssid, out);
}
bool sw_proxy_muse_enabled(void)
{
    sw_proxy_config_t config;
    sw_proxy_get(&config);
    return config.enabled;
}
esp_err_t sw_proxy_save_for(const char *ssid, const sw_proxy_config_t *c)
{
    sw_proxy_profiles_t next;
    xSemaphoreTake(lock, portMAX_DELAY);
    next = profiles;
    if (!sw_proxy_profile_set(&next, ssid, c)) { xSemaphoreGive(lock); return ESP_ERR_INVALID_ARG; }
    nvs_handle_t nvs;
    esp_err_t err = nvs_open("sw_net", NVS_READWRITE, &nvs);
    if (err == ESP_OK) {
        err = nvs_set_blob(nvs, "profiles_v2", &next, sizeof(next));
        if (err == ESP_OK) err = nvs_commit(nvs);
        nvs_close(nvs);
    }
    if (err == ESP_OK) profiles = next;
    xSemaphoreGive(lock);
    return err;
}
esp_err_t sw_proxy_init(void)
{
    lock = xSemaphoreCreateMutex(); if (!lock) return ESP_ERR_NO_MEM;
    nvs_handle_t nvs;
    if (nvs_open("sw_net", NVS_READONLY, &nvs) != ESP_OK) return ESP_OK;
    sw_proxy_profiles_t saved = {0}; size_t size = sizeof(saved);
    esp_err_t err = nvs_get_blob(nvs, "profiles_v2", &saved, &size);
    if (err == ESP_OK) {
        nvs_close(nvs);
        if (size != sizeof(saved) || !sw_proxy_profiles_valid(&saved)) { ESP_LOGW("sw_proxy","invalid profiles; configure in setup");return ESP_OK; }
        profiles = saved; return ESP_OK;
    }
    /* Only migrate when v2 is absent. Never resurrect a disabled old proxy. */
    if (err != ESP_ERR_NVS_NOT_FOUND) { nvs_close(nvs); return err; }
    sw_proxy_config_t legacy = {0}; size = sizeof(legacy);
    err = nvs_get_blob(nvs, "proxy_v1", &legacy, &size);
    nvs_close(nvs);
    if (err == ESP_ERR_NVS_NOT_FOUND) return ESP_OK;
    if (err != ESP_OK) return err;
    if (size != sizeof(legacy) || !memchr(legacy.host, 0, sizeof(legacy.host))) { ESP_LOGW("sw_proxy","invalid legacy proxy; configure in setup");return ESP_OK; }
    char ssid[33]; preferred_ssid(ssid);
    if (legacy.enabled && !ssid[0]) { ESP_LOGW("sw_proxy","legacy proxy needs a Wi-Fi profile; configure in setup");return ESP_OK; }
    if (ssid[0]) return sw_proxy_save_for(ssid, &legacy);
    return ESP_OK;
}
bool sw_proxy_request(const char *host, uint16_t port)
{
    char ssid[33]; if (!active_ssid(ssid)) preferred_ssid(ssid);
    if (!ssid[0] || !host || strlen(host) >= sizeof(pending.host) || (*host && (!sw_proxy_lan_ipv4(host) || !port))) return false;
    xSemaphoreTake(lock, portMAX_DELAY);
    memset(&pending, 0, sizeof(pending)); strcpy(pending.host, host);
    strcpy(pending_ssid, ssid); pending.port = port; pending.enabled = *host != 0; requested = true;
    xSemaphoreGive(lock); return true;
}
void sw_proxy_tick(void)
{
    sw_proxy_config_t c; char ssid[33]; bool apply;
    xSemaphoreTake(lock, portMAX_DELAY); apply = requested; c = pending;
    strcpy(ssid, pending_ssid); requested = false; xSemaphoreGive(lock);
    if (!apply) return;
    esp_err_t err = sw_proxy_save_for(ssid, &c);
    ESP_LOGI("sw_proxy", "network profile %s", err == ESP_OK ? "saved; restarting" : "save failed");
    if (err == ESP_OK) { vTaskDelay(pdMS_TO_TICKS(300)); esp_restart(); }
}

int __wrap_lwip_getaddrinfo(const char *host,const char *service,const struct addrinfo *hint,struct addrinfo **out)
{
    if (!sw_proxy_target(host)) return __real_lwip_getaddrinfo(host,service,hint,out);
    char ssid[33]; active_ssid(ssid);
    sw_proxy_config_t c;sw_proxy_get_for(ssid,&c);
    if (!c.enabled||!sw_proxy_target(host)) return __real_lwip_getaddrinfo(host,service,hint,out);
    if (strlen(host)>=sizeof(names[0])) return EAI_NONAME;
    int index=-1;
    xSemaphoreTake(lock,portMAX_DELAY);
    for (unsigned i=0;i<SLOTS;++i) if (!strcmp(names[i],host) && !strcmp(name_ssids[i],ssid)) { index=i;break; }
    if (index<0) for (unsigned i=0;i<SLOTS;++i) if (!names[i][0]) { strcpy(names[i],host);strcpy(name_ssids[i],ssid);index=i;break; }
    xSemaphoreGive(lock);
    if (index<0) return EAI_MEMORY;
    char ip[20];snprintf(ip,sizeof(ip),"198.19.255.%u",(unsigned)index+1);
    struct addrinfo ipv4=hint?*hint:(struct addrinfo){0};ipv4.ai_family=AF_INET;
    return __real_lwip_getaddrinfo(ip,service,&ipv4,out);
}
static bool wait_fd(int fd,bool writing,int64_t deadline)
{
    for (;;) {
        int64_t left=deadline-esp_timer_get_time();
        if (left<=0) { errno=ETIMEDOUT;return false; }
        fd_set fds;FD_ZERO(&fds);FD_SET(fd,&fds);
        struct timeval timeout={.tv_sec=left/1000000,.tv_usec=left%1000000};
        int n=select(fd+1,writing?NULL:&fds,writing?&fds:NULL,NULL,&timeout);
        if (n>0) return true;
        if (n<0&&errno==EINTR) continue;
        if (!n) errno=ETIMEDOUT;
        return false;
    }
}
static bool transfer(int fd,unsigned char *buf,size_t size,bool writing,int64_t deadline)
{
    size_t at=0;
    while (at<size) {
        if (!wait_fd(fd,writing,deadline)) return false;
        int n=writing?send(fd,buf+at,size-at,0):recv(fd,buf+at,size-at,0);
        if (n>0) at+=n;
        else if (n<0&&(errno==EINTR||errno==EAGAIN||errno==EWOULDBLOCK)) continue;
        else { if (!n) errno=ECONNRESET;return false; }
    }
    return true;
}
int __wrap_lwip_connect(int fd,const struct sockaddr *address,socklen_t size)
{
    if (!address||address->sa_family!=AF_INET||size<sizeof(struct sockaddr_in)) return __real_lwip_connect(fd,address,size);
    const struct sockaddr_in *dst=(const struct sockaddr_in *)address;
    uint32_t ip=ntohl(dst->sin_addr.s_addr);
    if ((ip&0xffffff00)!=0xc613ff00) return __real_lwip_connect(fd,address,size);
    unsigned index=(ip&255)-1;
    char host[254]={0};sw_proxy_config_t c;sw_proxy_get(&c);
    if (index<SLOTS&&lock) { xSemaphoreTake(lock,portMAX_DELAY);strcpy(host,names[index]);xSemaphoreGive(lock); }
    char ssid[33];
    if (!c.enabled || !host[0] || !active_ssid(ssid) || strcmp(ssid,name_ssids[index])) { errno=EHOSTUNREACH;return -1; }
    struct sockaddr_in proxy={.sin_family=AF_INET,.sin_port=htons(c.port)};
    if (inet_pton(AF_INET,c.host,&proxy.sin_addr)!=1) { errno=EINVAL;return -1; }
    int flags=fcntl(fd,F_GETFL,0);
    if (flags<0||fcntl(fd,F_SETFL,flags|O_NONBLOCK)<0) return -1;
    int64_t deadline=esp_timer_get_time()+10LL*1000000;
    int rc=__real_lwip_connect(fd,(struct sockaddr *)&proxy,sizeof(proxy));
    bool ok=rc==0;
    if (rc<0&&errno==EINPROGRESS&&wait_fd(fd,true,deadline)) {
        int error=0;socklen_t len=sizeof(error);
        ok=getsockopt(fd,SOL_SOCKET,SO_ERROR,&error,&len)==0&&!error;
        if (error) errno=error;
    }
    unsigned char data[260]={5,1,0};
    if (ok) ok=transfer(fd,data,3,true,deadline)&&transfer(fd,data,2,false,deadline);
    if (ok && (data[0]!=5||data[1]!=0)) { errno=EACCES;ok=false; }
    size_t n=sw_socks_request(host,ntohs(dst->sin_port),data,sizeof(data));
    if (ok) ok=n&&transfer(fd,data,n,true,deadline)&&transfer(fd,data,4,false,deadline);
    if (ok && (data[0]!=5||data[1]!=0||data[2]!=0)) { errno=ECONNREFUSED;ok=false; }
    if (ok) {
        unsigned type=data[3];n=type==1?6:type==4?18:0;
        if (type==3) { ok=transfer(fd,data,1,false,deadline);n=data[0]+2; }
        if (!n) { errno=EPROTO;ok=false; }
        if (ok) ok=transfer(fd,data,n,false,deadline);
    }
    int error=errno;fcntl(fd,F_SETFL,flags);
    if (!ok) { ESP_LOGW("sw_proxy","Muse SOCKS5 connection failed errno=%d",error);errno=error;return -1; }
    ESP_LOGI("sw_proxy","Muse SOCKS5 tunnel ready");
    return 0;
}
