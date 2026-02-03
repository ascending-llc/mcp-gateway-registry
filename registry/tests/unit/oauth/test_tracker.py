import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from registry.auth.oauth.reconnection.tracker import OAuthReconnectionTracker


@pytest.fixture
def tracker_and_data():
    """Fixture that provides tracker and test data for all tests."""
    tracker = OAuthReconnectionTracker()
    return {
        "tracker": tracker,
        "user_id": "user_id",
        "server_name": "server_name",
        "another_server": "another_server"
    }


@pytest.mark.unit
class TestOAuthReconnectionTracker:

    # ========== setFailed tests ==========
    def test_set_failed_should_record_failed_reconnection_attempt(self, tracker_and_data):
        """Should record failed reconnection attempt"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        tracker.set_failed(user_id, server_name)
        assert tracker.is_failed(user_id, server_name) == True

    def test_set_failed_should_track_multiple_servers_for_same_user(self, tracker_and_data):
        """Should track multiple servers for same user"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]
        another_server = tracker_and_data["another_server"]

        tracker.set_failed(user_id, server_name)
        tracker.set_failed(user_id, another_server)

        assert tracker.is_failed(user_id, server_name) == True
        assert tracker.is_failed(user_id, another_server) == True

    # ========== isFailed tests ==========
    def test_is_failed_should_return_false_when_no_failed_attempt_recorded(self, tracker_and_data):
        """Should return False when no failed attempt recorded"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        assert tracker.is_failed(user_id, server_name) == False

    def test_is_failed_should_return_true_after_failed_attempt_recorded(self, tracker_and_data):
        """Should return True after failed attempt recorded"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        tracker.set_failed(user_id, server_name)
        assert tracker.is_failed(user_id, server_name) == True

    def test_is_failed_should_return_false_for_different_server(self, tracker_and_data):
        """Should return False for different server, even if another server failed"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]
        another_server = tracker_and_data["another_server"]

        tracker.set_failed(user_id, server_name)
        assert tracker.is_failed(user_id, another_server) == False

    # ========== removeFailed tests ==========
    def test_remove_failed_should_clear_failed_reconnect_record(self, tracker_and_data):
        """Should clear failed reconnect record"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        tracker.set_failed(user_id, server_name)
        assert tracker.is_failed(user_id, server_name) == True

        tracker.remove_failed(user_id, server_name)
        assert tracker.is_failed(user_id, server_name) == False

    def test_remove_failed_should_only_clear_specific_server(self, tracker_and_data):
        """Should only clear specific server"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]
        another_server = tracker_and_data["another_server"]

        tracker.set_failed(user_id, server_name)
        tracker.set_failed(user_id, another_server)

        tracker.remove_failed(user_id, server_name)

        assert tracker.is_failed(user_id, server_name) == False
        assert tracker.is_failed(user_id, another_server) == True

    # ========== setActive tests ==========
    def test_set_active_should_mark_server_as_reconnecting(self, tracker_and_data):
        """Should mark server as reconnecting"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True

    def test_set_active_should_track_multiple_reconnecting_servers(self, tracker_and_data):
        """Should track multiple reconnecting servers"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]
        another_server = tracker_and_data["another_server"]

        tracker.set_active(user_id, server_name)
        tracker.set_active(user_id, another_server)

        assert tracker.is_active(user_id, server_name) == True
        assert tracker.is_active(user_id, another_server) == True

    # ========== isActive tests ==========
    def test_is_active_should_return_false_when_server_not_reconnecting(self, tracker_and_data):
        """Should return False when server is not reconnecting"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        assert tracker.is_active(user_id, server_name) == False

    def test_is_active_should_return_true_when_server_marked_as_reconnecting(self, tracker_and_data):
        """Should return True when server marked as reconnecting"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True

    def test_is_active_should_handle_non_existent_user_gracefully(self, tracker_and_data):
        """Should handle non-existent user gracefully"""
        tracker = tracker_and_data["tracker"]
        server_name = tracker_and_data["server_name"]

        assert tracker.is_active("non-existent-user", server_name) == False

    # ========== removeActive tests ==========
    def test_remove_active_should_clear_reconnecting_state(self, tracker_and_data):
        """Should clear reconnecting state"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True

        tracker.remove_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == False

    def test_remove_active_should_only_clear_specific_server_state(self, tracker_and_data):
        """Should only clear specific server state"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]
        another_server = tracker_and_data["another_server"]

        tracker.set_active(user_id, server_name)
        tracker.set_active(user_id, another_server)

        tracker.remove_active(user_id, server_name)

        assert tracker.is_active(user_id, server_name) == False
        assert tracker.is_active(user_id, another_server) == True

    def test_remove_active_should_handle_clearing_non_existent_state_gracefully(self, tracker_and_data):
        """Should handle clearing non-existent state gracefully"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        # Should not raise exception
        tracker.remove_active(user_id, server_name)
        assert True  # Just to have an assertion

    # ========== Cleanup behavior tests ==========
    def test_cleanup_empty_user_sets_for_failed_reconnects(self, tracker_and_data):
        """Should cleanup empty user sets for failed reconnects"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        tracker.set_failed(user_id, server_name)
        tracker.remove_failed(user_id, server_name)

        # Record and clear another user to ensure internal cleanup
        another_user_id = "user456"
        tracker.set_failed(another_user_id, server_name)

        # Original user should still be able to reconnect
        assert tracker.is_failed(user_id, server_name) == False

    def test_cleanup_empty_user_sets_for_active_reconnections(self, tracker_and_data):
        """Should cleanup empty user sets for active reconnections"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        tracker.set_active(user_id, server_name)
        tracker.remove_active(user_id, server_name)

        # Mark another user to ensure internal cleanup
        another_user_id = "user456"
        tracker.set_active(another_user_id, server_name)

        # Original user should not be reconnecting
        assert tracker.is_active(user_id, server_name) == False

    # ========== Combined state management tests ==========
    def test_combined_state_management(self, tracker_and_data):
        """Should handle failure and reconnecting states independently"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        # Mark as reconnecting
        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True
        assert tracker.is_failed(user_id, server_name) == False

        # Record failed attempt
        tracker.set_failed(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True
        assert tracker.is_failed(user_id, server_name) == True

        # Clear reconnecting state
        tracker.remove_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == False
        assert tracker.is_failed(user_id, server_name) == True

        # Clear failed state
        tracker.remove_failed(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == False
        assert tracker.is_failed(user_id, server_name) == False

    # ========== Timeout behavior tests ==========
    @patch("time.time")
    def test_should_track_timestamp_when_setting_active_state(self, mock_time, tracker_and_data):
        """Should track timestamp when setting active state"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True

        # Verify timestamp is recorded
        mock_time.return_value = now + 1  # 1 second later
        assert tracker.is_active(user_id, server_name) == True

    @patch("time.time")
    def test_should_handle_timeout_checking_with_is_still_reconnecting(self, mock_time, tracker_and_data):
        """Should handle timeout checking with is_still_reconnecting"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)
        assert tracker.is_still_reconnecting(user_id, server_name) == True

        # Advance 2 minutes 59 seconds - should still be reconnecting
        mock_time.return_value = now + 2 * 60 + 59
        assert tracker.is_still_reconnecting(user_id, server_name) == True

        # Advance 2 more seconds (total 3 minutes 1 second) - should no longer be reconnecting
        mock_time.return_value = now + 3 * 60 + 1
        assert tracker.is_still_reconnecting(user_id, server_name) == False

        # But is_active should still return True (simple check)
        assert tracker.is_active(user_id, server_name) == True

    @patch("time.time")
    def test_should_handle_multiple_servers_with_different_timeout_periods(self, mock_time, tracker_and_data):
        """Should handle multiple servers with different timeout periods"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]
        another_server = tracker_and_data["another_server"]

        now = 1000.0
        mock_time.return_value = now

        # Set server1 as active
        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True

        # Advance 3 minutes
        mock_time.return_value = now + 3 * 60

        # Set server2 as active
        tracker.set_active(user_id, another_server)
        assert tracker.is_active(user_id, another_server) == True
        assert tracker.is_active(user_id, server_name) == True

        # Advance another 2 minutes + 1ms (server1 at 5min 1ms, server2 at 2min 1ms)
        mock_time.return_value = now + 5 * 60 + 0.001
        assert tracker.is_still_reconnecting(user_id, server_name) == False  # server1 timeout
        assert tracker.is_still_reconnecting(user_id, another_server) == True  # server2 still active

        # Advance another 3 minutes (server2 at 5min 1ms)
        mock_time.return_value = now + 8 * 60 + 0.001
        assert tracker.is_still_reconnecting(user_id, another_server) == False  # server2 timeout

    @patch("time.time")
    def test_should_clear_timestamp_when_removing_active_state(self, mock_time, tracker_and_data):
        """Should clear timestamp when removing active state"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True

        tracker.remove_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == False

        # Set as active again and verify using new timestamp
        mock_time.return_value = now + 3 * 60
        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True

        # Advance 4 minutes from new timestamp - should still be active
        mock_time.return_value = now + 7 * 60
        assert tracker.is_active(user_id, server_name) == True

    @patch("time.time")
    def test_should_properly_cleanup_after_timeout_occurs(self, mock_time, tracker_and_data):
        """Should properly cleanup after timeout occurs"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]
        another_server = tracker_and_data["another_server"]

        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)
        tracker.set_active(user_id, another_server)
        assert tracker.is_active(user_id, server_name) == True
        assert tracker.is_active(user_id, another_server) == True

        # Advance past timeout period
        mock_time.return_value = now + 6 * 60

        # Both should still be in active set but not "still reconnecting"
        assert tracker.is_active(user_id, server_name) == True
        assert tracker.is_active(user_id, another_server) == True
        assert tracker.is_still_reconnecting(user_id, server_name) == False
        assert tracker.is_still_reconnecting(user_id, another_server) == False

        # Cleanup both
        assert tracker.cleanup_if_timed_out(user_id, server_name) == True
        assert tracker.cleanup_if_timed_out(user_id, another_server) == True

        # Now they should be removed from active set
        assert tracker.is_active(user_id, server_name) == False
        assert tracker.is_active(user_id, another_server) == False

    @patch("time.time")
    def test_should_handle_timeout_check_for_non_existent_entries_gracefully(self, mock_time, tracker_and_data):
        """Should handle timeout check for non-existent entries gracefully"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        now = 1000.0
        mock_time.return_value = now

        # Check non-existent entries
        assert tracker.is_active("non-existent", "non-existent") == False
        assert tracker.is_still_reconnecting("non-existent", "non-existent") == False

        # Set then manually remove
        tracker.set_active(user_id, server_name)
        tracker.remove_active(user_id, server_name)

        # Advance time and check - should not raise exception
        mock_time.return_value = now + 6 * 60
        assert tracker.is_active(user_id, server_name) == False
        assert tracker.is_still_reconnecting(user_id, server_name) == False

    # ========== isStillReconnecting tests ==========
    @patch("time.time")
    def test_is_still_reconnecting_should_return_true_for_active_entries_within_timeout(self, mock_time,
                                                                                        tracker_and_data):
        """Should return True for active entries within timeout"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)
        assert tracker.is_still_reconnecting(user_id, server_name) == True

        # Still within timeout
        mock_time.return_value = now + 3 * 60
        assert tracker.is_still_reconnecting(user_id, server_name) == True

    @patch("time.time")
    def test_is_still_reconnecting_should_return_false_for_timed_out_entries(self, mock_time, tracker_and_data):
        """Should return False for timed out entries"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)

        # Advance past timeout period
        mock_time.return_value = now + 6 * 60

        # Should no longer be reconnecting
        assert tracker.is_still_reconnecting(user_id, server_name) == False

        # But is_active should still return True (simple check)
        assert tracker.is_active(user_id, server_name) == True

    def test_is_still_reconnecting_should_return_false_for_non_existent_entries(self, tracker_and_data):
        """Should return False for non-existent entries"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        assert tracker.is_still_reconnecting("non-existent", "non-existent") == False
        assert tracker.is_still_reconnecting(user_id, server_name) == False

    # ========== cleanupIfTimedOut tests ==========
    @patch("time.time")
    def test_cleanup_if_timed_out_should_cleanup_and_return_true(self, mock_time, tracker_and_data):
        """Should cleanup timed out entries and return True"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True

        # Advance past timeout period
        mock_time.return_value = now + 6 * 60

        # Cleanup should return True and remove entry
        was_cleaned_up = tracker.cleanup_if_timed_out(user_id, server_name)
        assert was_cleaned_up == True
        assert tracker.is_active(user_id, server_name) == False

    @patch("time.time")
    def test_cleanup_if_timed_out_should_not_cleanup_active_entries_and_return_false(self, mock_time, tracker_and_data):
        """Should not cleanup active entries and return False"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)

        # Within timeout period
        mock_time.return_value = now + 3 * 60

        was_cleaned_up = tracker.cleanup_if_timed_out(user_id, server_name)
        assert was_cleaned_up == False
        assert tracker.is_active(user_id, server_name) == True

    def test_cleanup_if_timed_out_should_return_false_for_non_existent_entries(self, tracker_and_data):
        """Should return False for non-existent entries"""
        tracker = tracker_and_data["tracker"]

        was_cleaned_up = tracker.cleanup_if_timed_out("non-existent", "non-existent")
        assert was_cleaned_up == False

    # ========== Timestamp tracking edge case tests ==========
    @patch("time.time")
    def test_should_update_timestamp_when_setting_active_on_already_active_server(self, mock_time, tracker_and_data):
        """Should update timestamp when setting active on already active server"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)
        assert tracker.is_active(user_id, server_name) == True

        # Advance 3 minutes
        mock_time.return_value = now + 3 * 60
        assert tracker.is_active(user_id, server_name) == True

        # Set as active again - should reset timestamp
        tracker.set_active(user_id, server_name)

        # Advance 4 minutes from reset point (total 7 minutes from start)
        mock_time.return_value = now + 7 * 60
        # Should still be active because timestamp reset at 3 minutes
        assert tracker.is_active(user_id, server_name) == True

        # Advance another 2 minutes (6 minutes from reset)
        mock_time.return_value = now + 9 * 60
        # Should no longer be reconnecting (timed out)
        assert tracker.is_still_reconnecting(user_id, server_name) == False

    @patch("time.time")
    def test_should_handle_same_server_for_different_users_independently(self, mock_time, tracker_and_data):
        """Should handle same server for different users independently"""
        tracker = tracker_and_data["tracker"]
        user_id = tracker_and_data["user_id"]
        server_name = tracker_and_data["server_name"]

        another_user_id = "user456"
        now = 1000.0
        mock_time.return_value = now

        tracker.set_active(user_id, server_name)

        # Advance 3 minutes
        mock_time.return_value = now + 3 * 60

        tracker.set_active(another_user_id, server_name)

        # Advance another 3 minutes
        mock_time.return_value = now + 6 * 60

        # First user's connection should timeout
        assert tracker.is_still_reconnecting(user_id, server_name) == False
        # Second user's connection should still be reconnecting
        assert tracker.is_still_reconnecting(another_user_id, server_name) == True
