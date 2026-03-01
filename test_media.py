
import sys
import os
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())

from Jarvis.core.system.action_router import ActionRouter, ActionRequest, ActionType
from Jarvis.core.system.windows import WindowsBackend

from Jarvis.core.system.actions import ActionResult, ActionType, RiskLevel

def test_media_routing():
    backend = WindowsBackend()
    # Mock open_url to avoid actual browser launch
    backend.open_url = MagicMock(return_value=ActionResult(success=True, message="URL opened", action_type=ActionType.OPEN_URL, risk_level=RiskLevel.LOW))
    backend.launch_app = MagicMock(return_value=ActionResult(success=True, message="App launched", action_type=ActionType.LAUNCH_APP, risk_level=RiskLevel.LOW))
    
    router = ActionRouter(backend)
    
    # Test YouTube routing
    req_yt = ActionRequest(ActionType.PLAY_MUSIC, "lofi beats on youtube")
    router.execute_action(req_yt)
    backend.open_url.assert_called_with("https://www.youtube.com/results?search_query=lofi+beats")
    print("YouTube routing passed!")
    
    # Test Spotify routing
    req_spot = ActionRequest(ActionType.PLAY_MUSIC, "metallica on spotify")
    router.execute_action(req_spot)
    backend.launch_app.assert_called_with("spotify:search:metallica")
    print("Spotify routing passed!")

if __name__ == "__main__":
    test_media_routing()
