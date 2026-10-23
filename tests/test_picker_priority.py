import unittest

from hopline.picker import NodePicker


class PickerPriorityTests(unittest.TestCase):
    def test_healthy_nodes_are_preferred_over_unknown_and_degraded(self) -> None:
        states = {"known": "healthy", "unproven": "unknown", "weak": "degraded"}
        picker = NodePicker(["unproven", "weak", "known"], state=lambda node_id: states[node_id])
        candidates = picker.candidates("rotate")
        self.assertEqual(candidates[0], "known")
        self.assertEqual(set(candidates[1:]), {"unproven", "weak"})

    def test_unknown_nodes_still_used_as_fallback(self) -> None:
        picker = NodePicker(["a", "b"], state=lambda _node_id: "unknown")
        self.assertEqual(picker.candidates("rotate"), ["a", "b"])

    def test_dead_and_quarantine_stay_excluded(self) -> None:
        states = {"healthy": "healthy", "dead": "dead", "q": "quarantine", "unknown": "unknown"}
        picker = NodePicker(["dead", "q", "unknown", "healthy"], state=lambda n: states[n])
        self.assertEqual(picker.candidates("rotate"), ["healthy", "unknown"])

    def test_forced_node_ignores_priority(self) -> None:
        states = {"known": "healthy", "unproven": "unknown"}
        picker = NodePicker(["known", "unproven"], state=lambda n: states[n])
        self.assertEqual(picker.candidates("unproven"), ["unproven"])


if __name__ == "__main__":
    unittest.main()
