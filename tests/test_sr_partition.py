import ctypes
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SpeechPartitionTests(unittest.TestCase):
    def test_flash_metadata_and_assets_before_vendor_loader(self):
        headers = {
            'esp_err.h': "#pragma once\ntypedef int esp_err_t;\nenum {ESP_OK, ESP_FAIL, ESP_ERR_NOT_FOUND, ESP_ERR_INVALID_SIZE, ESP_ERR_INVALID_RESPONSE, ESP_ERR_NOT_SUPPORTED, ESP_ERR_NO_MEM, ESP_ERR_INVALID_CRC};\n",
            'esp_partition.h': "#include <stddef.h>\n#include <stdint.h>\n#include \"esp_err.h\"\ntypedef struct {size_t size;} esp_partition_t;\n#define ESP_PARTITION_TYPE_DATA 1\n#define ESP_PARTITION_SUBTYPE_ANY 255\n#define ESP_PARTITION_MMAP_DATA 0\nconst esp_partition_t *esp_partition_find_first(int, int, const char *);\nesp_err_t esp_partition_read(const esp_partition_t *, size_t, void *, size_t);\n",
            'esp_heap_caps.h': "#include <stddef.h>\n#define MALLOC_CAP_SPIRAM 1\n#define MALLOC_CAP_8BIT 2\nvoid *heap_caps_malloc(size_t,int);\nvoid heap_caps_free(void *);\nsize_t heap_caps_get_largest_free_block(int);\n",
            'spi_flash_mmap.h': 'int spi_flash_mmap_get_free_pages(int);\n',
            'mbedtls/md.h': "#include <stddef.h>\n#define MBEDTLS_MD_SHA256 1\ntypedef int mbedtls_md_info_t;\nconst mbedtls_md_info_t *mbedtls_md_info_from_type(int);\nint mbedtls_md(const mbedtls_md_info_t *, const unsigned char *, size_t, unsigned char *);\n",
        }
        shim = r'''
#include <stdlib.h>
#include <string.h>
#include "esp_partition.h"
#include "mbedtls/md.h"
static const unsigned char *image;
static size_t image_size;
static esp_partition_t partition = {2097152};
static int mode;
static int (*digest)(const unsigned char *, size_t, unsigned char *);
void configure(const unsigned char *p, size_t n, int m,
               int (*hash)(const unsigned char *, size_t, unsigned char *)) {
 image=p; image_size=n; mode=m; digest=hash;
}
const esp_partition_t *esp_partition_find_first(int t,int s,const char *n) {
 (void)t; (void)s; (void)n; return mode==1 ? NULL : &partition;
}
esp_err_t esp_partition_read(const esp_partition_t *p,size_t o,void *out,size_t n) {
 (void)p; if(mode==2 || o>image_size || n>image_size-o) return ESP_FAIL;
 memcpy(out,image+o,n); return ESP_OK;
}
void *heap_caps_malloc(size_t n,int c) { (void)c; return mode==3 ? NULL : malloc(n); }
void heap_caps_free(void *p) {free(p);}
size_t heap_caps_get_largest_free_block(int c) { (void)c; return mode==5 ? 0 : 65536; }
int spi_flash_mmap_get_free_pages(int c) { (void)c; return mode==4 ? 0 : 128; }
const mbedtls_md_info_t *mbedtls_md_info_from_type(int t) {static int x; (void)t; return &x;}
int mbedtls_md(const mbedtls_md_info_t *m,const unsigned char *p,size_t n,unsigned char *out) {
 (void)m; return digest(p,n,out);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            for name, text in headers.items():
                target = d / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            (d / 'shim.c').write_text(shim)
            base = ROOT / 'firmware/esp32/components/muse'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                            '-I', str(d), '-I', str(base), str(d / 'shim.c'),
                            str(base / 'muse_sr_partition.c'), '-o', str(d / 'guard.so')], check=True)
            lib = ctypes.CDLL(str(d / 'guard.so'))
            callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                             ctypes.c_size_t, ctypes.c_void_p)
            @callback_type
            def digest(data, size, out):
                ctypes.memmove(out, hashlib.sha256(ctypes.string_at(data, size)).digest(), 32)
                return 0
            lib.configure.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, callback_type]
            def validate(data, mode=0):
                buf = ctypes.create_string_buffer(data)
                lib.configure(buf, len(data), mode, digest)
                return lib.muse_sr_partition_validate()
            self.assertNotEqual(validate(bytes([255]) * 160), 0)
            self.assertNotEqual(validate(bytes(160)), 0)
            self.assertNotEqual(validate(bytes(160), 1), 0)
            self.assertNotEqual(validate(bytes(160), 2), 0)
            # Real pinned public model when present: SHA-256 is Python hashlib,
            # while the checked parser, bounds and admission logic are production C.
            model = ROOT / 'build-musestack-camera-handsfree-text/srmodels/srmodels.bin'
            if model.exists():
                packed = model.read_bytes()
                self.assertEqual(validate(packed), 0)
                for mode in (1, 2, 3, 4, 5):
                    self.assertNotEqual(validate(packed, mode), 0)
                for offset in (0, 4, 36, 40, 72, 76, 160, len(packed)-1):
                    changed = bytearray(packed); changed[offset] ^= 255
                    self.assertNotEqual(validate(bytes(changed)), 0, offset)
                changed = bytearray(packed)
                struct.pack_into('<I', changed, 72, 0xfffffff0)
                self.assertNotEqual(validate(bytes(changed)), 0)
                self.assertNotEqual(validate(packed[:-1]), 0)
