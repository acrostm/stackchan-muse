// SPDX-License-Identifier: Apache-2.0
#pragma once

typedef enum {
    STACKCHAN_EXPRESSION_NOD,
    STACKCHAN_EXPRESSION_AFFIRM,
    STACKCHAN_EXPRESSION_THINK,
    STACKCHAN_EXPRESSION_APOLOGY,
    STACKCHAN_EXPRESSION_HAPPY,
} stackchan_expression_t;

/* Conservative local interpretation of finished reply text. This chooses a
 * small gesture only; it never changes the answer or calls another model. */
stackchan_expression_t stackchan_expression_plan(const char *text);
