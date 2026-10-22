// SPDX-License-Identifier: Apache-2.0
#include "muse_sr_partition.h"
#include <stdint.h>
#include <string.h>
#include "esp_heap_caps.h"
#include "esp_partition.h"
#include "spi_flash_mmap.h"
#include "mbedtls/md.h"

/* Pinned to docs/speech-models.lock.json. Validate before the vendor parser,
 * which trusts flash offsets and aborts on mmap errors. */
static const struct { const char *name; uint32_t bytes; const char *sha; } assets[] = {
    {"_MODEL_INFO_", 45u, "96b2615dc51d471796fd5da91330c33733a8ff45ee465692cc630fddbda4572a"},
    {"wn9_data", 289665u, "dbba353b4b5cb923984de753012671aa122cd4373739173956d2071ba9618eb3"},
    {"wn9_index", 1200u, "5810ee84beac8e73b4080a7b765e09900627ff973f2654811dd6a8557f0769b4"},
};
static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static bool fixed_name(const uint8_t *p, const char *name)
{
    const size_t n = strlen(name);
    if (n >= 32 || memcmp(p, name, n)) return false;
    for (size_t i = n; i < 32; ++i) if (p[i]) return false;
    return true;
}
esp_err_t muse_sr_partition_validate(void)
{
    const esp_partition_t *part = esp_partition_find_first(ESP_PARTITION_TYPE_DATA,
                                                         ESP_PARTITION_SUBTYPE_ANY, "model");
    if (!part) return ESP_ERR_NOT_FOUND;
    if (part->size != 2097152u) return ESP_ERR_INVALID_SIZE;
    uint8_t header[160];
    esp_err_t error = esp_partition_read(part, 0, header, sizeof(header));
    if (error != ESP_OK) return error;
    if (le32(header) != 1 || !fixed_name(header+4, "wn9_histackchan_tts3") ||
        le32(header+36) != 3) return ESP_ERR_INVALID_RESPONSE;
    uint32_t next = sizeof(header);
    unsigned seen = 0;
    const mbedtls_md_info_t *md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!md) return ESP_ERR_NOT_SUPPORTED;
    for (unsigned i = 0; i < 3; ++i) {
        const uint8_t *record = header+40+i*40;
        unsigned index = 0;
        while (index < 3 && !fixed_name(record, assets[index].name)) ++index;
        if (index == 3 || (seen & (1u<<index))) return ESP_ERR_INVALID_RESPONSE;
        seen |= 1u<<index;
        uint32_t offset = le32(record+32), bytes = le32(record+36);
        if (offset != next || bytes != assets[index].bytes ||
            offset > part->size || bytes > part->size-offset) return ESP_ERR_INVALID_SIZE;
        next += bytes;
        uint8_t *data = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!data) return ESP_ERR_NO_MEM;
        uint8_t hash[32];
        error = esp_partition_read(part, offset, data, bytes);
        if (error == ESP_OK && mbedtls_md(md, data, bytes, hash)) error = ESP_FAIL;
        heap_caps_free(data);
        if (error != ESP_OK) return error;
        static const char hex[] = "0123456789abcdef";
        for (unsigned j = 0; j < 32; ++j)
            if (hex[hash[j]>>4] != assets[index].sha[2*j] ||
                hex[hash[j]&15] != assets[index].sha[2*j+1]) return ESP_ERR_INVALID_CRC;
    }
    /* Leave a mapping page spare for alignment/concurrent users. Memory checks
     * are admission checks, not a guarantee against concurrent allocation. */
    if (spi_flash_mmap_get_free_pages(ESP_PARTITION_MMAP_DATA) < 33 ||
        heap_caps_get_largest_free_block(MALLOC_CAP_8BIT) < 8192)
        return ESP_ERR_NO_MEM;
    return ESP_OK;
}
