import unittest

from web.components.drawer import NavigationState


class NavigationStateTests(unittest.TestCase):
    def test_running_task_blocks_its_own_exit_but_allows_return_from_other_page(self):
        navigation = NavigationState()
        navigation.lock("/videos/publishing", "Publishing is running")

        self.assertEqual(
            navigation.blocking_message("/videos/publishing", "/studio"),
            "Publishing is running",
        )
        self.assertIsNone(navigation.blocking_message("/studio", "/videos/publishing"))
        self.assertIsNone(navigation.blocking_message("/videos/publishing", "/videos/publishing"))

        navigation.unlock("/videos/publishing")
        self.assertIsNone(navigation.blocking_message("/videos/publishing", "/studio"))

    def test_finishing_another_job_does_not_unlock_running_publishing_task(self):
        navigation = NavigationState()
        navigation.lock("/videos/publishing", "Publishing is running")
        navigation.lock("/studio", "Studio scan is running")
        navigation.unlock("/studio")

        self.assertEqual(
            navigation.blocking_message("/videos/publishing", "/studio"),
            "Publishing is running",
        )
        self.assertIsNone(
            navigation.blocking_message("/studio", "/videos/publishing")
        )


if __name__ == "__main__":
    unittest.main()
