import json
import time
import uuid
from pathlib import Path


class VTubeStudioError(RuntimeError):
    pass


class VTubeStudio:
    def __init__(self, url: str, token_path: Path, plugin_name: str, developer: str):
        self.url = url
        self.token_path = token_path
        self.plugin_name = plugin_name
        self.developer = developer
        self.socket = None

    def connect(self) -> None:
        try:
            import websocket
            self.socket = websocket.create_connection(self.url, timeout=5)
        except Exception as exc:
            raise VTubeStudioError(f"VTube Studioへ接続できません: {exc}") from exc
        token = self.token_path.read_text(encoding="utf-8").strip() if self.token_path.exists() else ""
        if not token:
            result = self.request("AuthenticationTokenRequest", {
                "pluginName": self.plugin_name,
                "pluginDeveloper": self.developer,
            })
            token = result.get("data", {}).get("authenticationToken", "")
            if token:
                self.token_path.write_text(token, encoding="utf-8")
        result = self.request("AuthenticationRequest", {
            "pluginName": self.plugin_name,
            "pluginDeveloper": self.developer,
            "authenticationToken": token,
        })
        if not result.get("data", {}).get("authenticated"):
            raise VTubeStudioError("VTube Studioの認証に失敗しました")

    def request(self, message_type: str, data: dict | None = None) -> dict:
        if self.socket is None:
            raise VTubeStudioError("VTube Studioへ接続されていません")
        message = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": uuid.uuid4().hex,
            "messageType": message_type,
        }
        if data is not None:
            message["data"] = data
        self.socket.send(json.dumps(message, ensure_ascii=False))
        response = json.loads(self.socket.recv())
        if response.get("messageType") == "APIError":
            raise VTubeStudioError(response.get("data", {}).get("message", "VTube Studio API error"))
        return response

    def load_model(self, title: str) -> None:
        models = self.request("AvailableModelsRequest")
        candidates = models.get("data", {}).get("availableModels", [])
        model = next((item for item in candidates if item.get("modelName") == title or item.get("modelID") == title), None)
        if model is None:
            raise VTubeStudioError(f"モデルが見つかりません: {title}")
        self.request("ModelLoadRequest", {"modelID": model["modelID"]})
        time.sleep(1)

    def trigger(self, hotkey_name: str) -> bool:
        hotkeys = self.request("HotkeysInCurrentModelRequest").get("data", {}).get("availableHotkeys", [])
        hotkey = next((item for item in hotkeys if item.get("name") == hotkey_name or item.get("hotkeyID") == hotkey_name), None)
        if hotkey is None:
            return False
        self.request("HotkeyTriggerRequest", {"hotkeyID": hotkey["hotkeyID"]})
        return True

    def inject_mouth(self, value: float, parameter_id: str = "ParamMouthOpenY") -> None:
        """音声の音量から計算した口の開き具合をLive2Dへ送る。"""
        self.request("InjectParameterDataRequest", {
            "faceFound": True,
            "mode": "set",
            "parameterValues": [{"id": parameter_id, "value": max(0.0, min(1.0, value))}],
        })

    def ensure_custom_parameter(self, parameter_name: str = "AutoMouth") -> None:
        parameters = self.request("InputParameterListRequest").get("data", {}).get("defaultParameters", [])
        parameters += self.request("InputParameterListRequest").get("data", {}).get("customParameters", [])
        if any(item.get("name") == parameter_name for item in parameters):
            return
        self.request("ParameterCreationRequest", {
            "parameterName": parameter_name,
            "explanation": "AI音声の音量から口の開きを制御します。",
            "min": 0,
            "max": 1,
            "defaultValue": 0,
        })

    def close(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None
