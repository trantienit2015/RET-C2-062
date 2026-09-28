# RET-C2-062 - TC-06/TC-07: S-2/S-3 gates are @final on FunctionNode (overriding
# raises TypeError at class definition). Exact-name scaffold invariant file
# — kept separate from test_framework_compliance.py so the exact-name check finds it.
#
# Local wheel rc1 stub does not implement the @final decorator on
# FunctionNode._security_gate_input/_security_gate_output.
# CI wheel 1.0.0 is the
# gate of record; these tests are skipped locally when the base method is absent
# rather than asserting a false regression.

import pytest
from framework.nodes.function_node import FunctionNode

from src.nodes import report_narrate_node

pytestmark = pytest.mark.skipif(
    not hasattr(FunctionNode, "_security_gate_input"),
    reason="local wheel rc1 stub lacks S-2/S-3 @final gates — CI wheel 1.0.0 is gate of record",
)


class TestTC0607FinalGates:
    def test_input_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadIn(FunctionNode):  # noqa: N801
                def _security_gate_input(self, state):
                    return state

    def test_output_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadOut(FunctionNode):  # noqa: N801
                def _security_gate_output(self, result):
                    return result

    def test_extra_hook_is_overridable(self):
        assert (
            report_narrate_node.ReportNarrateNode._extra_security_gate_output
            is not FunctionNode._extra_security_gate_output
        )

    def test_output_gate_blocks_credentials(self):
        node = report_narrate_node.ReportNarrateNode()
        with pytest.raises(Exception):
            node._security_gate_output({"formatted_output": "token AKIAIOSFODNN7EXAMPLE leaked"})
