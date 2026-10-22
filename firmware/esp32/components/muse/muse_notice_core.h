// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define MUSE_NOTICE_QUEUE_MAX 4
#define MUSE_NOTICE_TEXT_MAX 16384
#define MUSE_NOTICE_SPEECH_BYTES 700
#define MUSE_NOTICE_SEEN_MAX 32

typedef enum {
    MUSE_NOTICE_ACCEPTED, MUSE_NOTICE_DUPLICATE, MUSE_NOTICE_FULL,
    MUSE_NOTICE_TOO_LONG, MUSE_NOTICE_INVALID_TEXT, MUSE_NOTICE_NO_MEMORY
} muse_notice_result_t;
typedef struct {
    char *text[MUSE_NOTICE_QUEUE_MAX];
    bool unread_only[MUSE_NOTICE_QUEUE_MAX];
    unsigned head, count;
    unsigned reserved;
    uint64_t seen[MUSE_NOTICE_SEEN_MAX];
    unsigned seen_next;
    void *(*allocate)(size_t);
    void (*release)(void *);
    muse_notice_result_t last_result;
} muse_notice_core_t;

bool muse_notice_core_publish(muse_notice_core_t *, const char *message_id, const char *text);
bool muse_notice_core_publish_mode(muse_notice_core_t *, const char *message_id, const char *text, bool unread_only);
/* A short destination never removes or truncates a message. */
bool muse_notice_core_take(muse_notice_core_t *, char *out, size_t cap);
bool muse_notice_core_take_mode(muse_notice_core_t *, char *out, size_t cap, bool include_unread);
/* Ownership transfer: the sole consumer returns the pointer or releases it. */
char *muse_notice_core_claim(muse_notice_core_t *, bool include_unread);
bool muse_notice_core_return_owned(muse_notice_core_t *, char *text);
void muse_notice_core_release(muse_notice_core_t *, char *text);
void muse_notice_core_clear(muse_notice_core_t *);
void muse_notice_core_silence(muse_notice_core_t *);
bool muse_notice_core_audible(const muse_notice_core_t *);
/* Copy the next complete-codepoint fragment. Offset advances only on success. */
size_t muse_notice_text_chunk(const char *text, size_t offset, char *out, size_t cap);
