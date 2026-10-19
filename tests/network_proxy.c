#include "proxy_stubs.h"
#include <assert.h>
#include <pthread.h>
#include "../firmware/esp32/components/muse/sw_proxy.c"
int __real_lwip_getaddrinfo(const char *h,const char *s,const struct addrinfo *v,struct addrinfo **out) { return getaddrinfo(h,s,v,out); }
int __real_lwip_connect(int fd,const struct sockaddr *a,socklen_t n) { return connect(fd,a,n); }
static int listener;
static bool reject_auth;
static void read_exact(int fd,unsigned char *b,size_t n) { for(size_t i=0;i<n;++i) assert(recv(fd,b+i,1,0)==1); }
static void *server(void *unused)
{
    (void)unused;int fd=accept(listener,NULL,NULL);assert(fd>=0);unsigned char data[300];
    read_exact(fd,data,3);assert(!memcmp(data,"\5\1\0",3));
    unsigned char auth[2]={5,reject_auth?2:0};
    assert(send(fd,auth,1,0)==1);assert(send(fd,auth+1,1,0)==1);
    if (!reject_auth) {
        read_exact(fd,data,5);assert(!memcmp(data,"\5\1\0\3",4));unsigned len=data[4];
        read_exact(fd,data,len+2);assert(len==11&&!memcmp(data,"api.muse.ai",11));assert(data[len]==1&&data[len+1]==187);
        const unsigned char reply[]={5,0,0,1,127,0,0,1,0,0};
        for(unsigned i=0;i<sizeof(reply);++i) assert(send(fd,reply+i,1,0)==1);
    }
    close(fd);return NULL;
}
int main(void)
{
    assert(sw_proxy_target("api.muse.ai"));assert(sw_proxy_target("HATCH.METAAIVM.COM."));
    assert(!sw_proxy_target("api.muse.ai.attacker.test"));assert(!sw_proxy_target("notmuse.ai"));assert(!sw_proxy_target("openspeech.bytedance.com"));
    assert(sw_proxy_lan_ipv4("192.168.1.4"));assert(sw_proxy_lan_ipv4("172.16.0.1"));assert(sw_proxy_lan_ipv4("10.0.0.2"));
    assert(!sw_proxy_lan_ipv4("127.0.0.1"));assert(!sw_proxy_lan_ipv4("172.32.0.1"));assert(!sw_proxy_lan_ipv4("192.168.1.256"));assert(!sw_proxy_lan_ipv4("192.168.1.1x"));
    unsigned char buf[300];assert(sw_socks_request("api.muse.ai",443,buf,sizeof(buf))==18);
    assert(!sw_socks_request("api.muse.ai\r\n",443,buf,sizeof(buf)));assert(!sw_socks_request("api.muse.ai",443,buf,4));
    sw_proxy_config_t legacy={.host="192.168.1.4",.port=7897,.enabled=true};
    memcpy(legacy_blob,&legacy,sizeof(legacy));legacy_size=sizeof(legacy);
    assert(sw_proxy_init()==ESP_OK);
    sw_proxy_config_t migrated;sw_proxy_get(&migrated);assert(migrated.enabled && migrated.port==7897);
    assert(profiles_size==sizeof(sw_proxy_profiles_t));
    strcpy(test_ssid,"phone");sw_proxy_get(&migrated);assert(!migrated.enabled);
    strcpy(test_ssid,"home");legacy.enabled=false;assert(sw_proxy_save_for("home",&legacy)==ESP_OK);
    pthread_mutex_destroy(lock);free(lock);profiles=(sw_proxy_profiles_t){0};
    assert(sw_proxy_init()==ESP_OK);sw_proxy_get(&migrated);assert(!migrated.enabled); /* Old enabled v1 cannot resurrect. */
    listener=socket(AF_INET,SOCK_STREAM,0);assert(listener>=0);
    struct sockaddr_in addr={.sin_family=AF_INET,.sin_addr.s_addr=htonl(0x7f000001)};
    assert(!bind(listener,(void *)&addr,sizeof(addr)));assert(!listen(listener,2));socklen_t size=sizeof(addr);assert(!getsockname(listener,(void *)&addr,&size));
    /* Loopback is injected only into the harness; production setters forbid it. */
    strcpy(profiles.entries[0].ssid,"home");
    profiles.entries[0].proxy=(sw_proxy_config_t){.enabled=true,.port=ntohs(addr.sin_port)};
    strcpy(profiles.entries[0].proxy.host,"127.0.0.1");
    struct addrinfo hint={.ai_family=AF_UNSPEC,.ai_socktype=SOCK_STREAM},*out;
    assert(!__wrap_lwip_getaddrinfo("api.muse.ai","443",&hint,&out));assert(out->ai_family==AF_INET);
    assert(ntohl(((struct sockaddr_in *)out->ai_addr)->sin_addr.s_addr)==0xc613ff01);
    for(unsigned attempt=0;attempt<2;++attempt) {
        reject_auth=attempt;pthread_t thread;assert(!pthread_create(&thread,NULL,server,NULL));
        int fd=socket(AF_INET,SOCK_STREAM,0);assert(fd>=0);int flags=fcntl(fd,F_GETFL,0);fcntl(fd,F_SETFL,flags|O_NONBLOCK);
        int rc=__wrap_lwip_connect(fd,out->ai_addr,out->ai_addrlen);
        if(reject_auth) assert(rc==-1&&errno==EACCES);else assert(rc==0);
        assert(fcntl(fd,F_GETFL,0)&O_NONBLOCK);close(fd);pthread_join(thread,NULL);
    }
    /* A cached synthetic destination must not carry the home proxy to a hotspot. */
    strcpy(test_ssid,"phone");
    sw_proxy_config_t selected;sw_proxy_get(&selected);assert(!selected.enabled);
    int stale=socket(AF_INET,SOCK_STREAM,0);assert(stale>=0);
    assert(__wrap_lwip_connect(stale,out->ai_addr,out->ai_addrlen)==-1 && errno==EHOSTUNREACH);
    close(stale);
    strcpy(test_ssid,"home");sw_proxy_get(&selected);assert(selected.enabled);
    freeaddrinfo(out);close(listener);
    for(unsigned i=1;i<SLOTS;++i) { char h[48];snprintf(h,sizeof(h),"node%u.muse.ai",i);assert(!__wrap_lwip_getaddrinfo(h,"443",&hint,&out));freeaddrinfo(out); }
    assert(__wrap_lwip_getaddrinfo("overflow.muse.ai","443",&hint,&out)==EAI_MEMORY);
    assert(!__wrap_lwip_getaddrinfo("localhost","443",&hint,&out));freeaddrinfo(out); /* Other domains stay direct. */
    pthread_mutex_destroy(lock); free(lock);
    puts("proxy protocol and socket routing: PASS");
}
