from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StackChanExpressionPlanTests(unittest.TestCase):
    def test_reply_text_selects_only_small_supported_gestures(self):
        source = r'''
#include "stackchan_expression_plan.h"
#include <assert.h>
int main(void) {
    assert(stackchan_expression_plan("好的，已经完成。") ==
           STACKCHAN_EXPRESSION_AFFIRM);
    assert(stackchan_expression_plan("可能还需要一点时间？") ==
           STACKCHAN_EXPRESSION_THINK);
    assert(stackchan_expression_plan("抱歉，操作失败了。") ==
           STACKCHAN_EXPRESSION_APOLOGY);
    assert(stackchan_expression_plan("Hello!") ==
           STACKCHAN_EXPRESSION_HAPPY);
    assert(stackchan_expression_plan("The weather is mild.") ==
           STACKCHAN_EXPRESSION_NOD);
    assert(stackchan_expression_plan("") == STACKCHAN_EXPRESSION_NOD);
    assert(stackchan_expression_plan(0) == STACKCHAN_EXPRESSION_NOD);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "test.c").write_text(source)
            binary = path / "test"
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined",
                "-I", str(ROOT / "firmware/esp32/components/muse/boards"),
                str(path / "test.c"),
                str(ROOT / "firmware/esp32/components/muse/boards/stackchan_expression_plan.c"),
                "-o", str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
