// SPDX-License-Identifier: Apache-2.0
#include "stackchan_expression_plan.h"

#include <stddef.h>
#include <string.h>

static int ascii_equal(int left, int right)
{
    return left >= 'A' && left <= 'Z' ? left + ('a' - 'A') == right
         : left >= 'a' && left <= 'z' ? left == right
         : left == right;
}

static int contains_ascii(const char *text, const char *needle)
{
    for (; *text; ++text) {
        const char *a = text;
        const char *b = needle;
        while (*a && *b &&
               ascii_equal((unsigned char)*a, (unsigned char)*b)) {
            ++a;
            ++b;
        }
        if (!*b) return 1;
    }
    return 0;
}

stackchan_expression_t stackchan_expression_plan(const char *text)
{
    if (!text || !text[0]) return STACKCHAN_EXPRESSION_NOD;
    const char *const apology[] = {
        "抱歉", "对不起", "无法", "失败", "错误", "出错了", "没成功",
        "sorry", "error", "failed", "cannot", "can't", "unable",
    };
    for (size_t i = 0; i < sizeof(apology) / sizeof(apology[0]); ++i)
        if (contains_ascii(text, apology[i])) return STACKCHAN_EXPRESSION_APOLOGY;

    if (strchr(text, '?') || strstr(text, "？") || contains_ascii(text, "吗") ||
        contains_ascii(text, "也许") || contains_ascii(text, "可能") ||
        contains_ascii(text, "perhaps") || contains_ascii(text, "maybe") ||
        contains_ascii(text, "not sure"))
        return STACKCHAN_EXPRESSION_THINK;

    const char *const happy[] = {
        "你好", "早上好", "晚上好", "太好了", "开心", "高兴", "欢迎",
        "hello", "hi ", "great", "happy", "welcome",
    };
    for (size_t i = 0; i < sizeof(happy) / sizeof(happy[0]); ++i)
        if (contains_ascii(text, happy[i])) return STACKCHAN_EXPRESSION_HAPPY;

    const char *const affirm[] = {
        "可以", "好的", "完成", "成功", "没问题", "已经", "当然",
        "done", "yes", "okay", "ready", "completed", "success",
    };
    for (size_t i = 0; i < sizeof(affirm) / sizeof(affirm[0]); ++i)
        if (contains_ascii(text, affirm[i])) return STACKCHAN_EXPRESSION_AFFIRM;
    return STACKCHAN_EXPRESSION_NOD;
}
