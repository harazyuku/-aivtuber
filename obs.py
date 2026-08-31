import base64
import hashlib
import json
import os
import uuid
from pathlib import Path


class OBSError(RuntimeError):
    pass


class OBS:
    def __init__(self, url: str, password: str = ""):
        self.url = url
        self.password = password
        self.socket = None
        self.request_id = 0

    def connect(self) -> None:
        try:
            import websocket
            self.socket = websocket.create_connection(self.url, timeout=5)
            hello = json.loads(self.socket.recv())
            identify = {"op": 1, "d": {"rpcVersion": 1}}
            auth = hello.get("d", {}).get("authentication")
            if auth:
                if not self.password:
                    raise OBSError("OBS WebSocketのパスワードが必要です")
                secret = base64.b64encode(hashlib.sha256((self.password + auth["salt"]).encode()).digest()).decode()
                auth_hash = base64.b64encode(hashlib.sha256((secret + auth["challenge"]).encode()).digest()).decode()
                identify["d"]["authentication"] = auth_hash
            self.socket.send(json.dumps(identify))
            response = json.loads(self.socket.recv())
            if response.get("op") != 2:
                raise OBSError(f"OBS認証に失敗しました: {response}")
        except OBSError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise OBSError(f"OBSへ接続できません: {exc}") from exc

    def request(self, request_type: str, request_data: dict | None = None) -> dict:
        self.request_id += 1
        request_id = str(self.request_id)
        message = {"op": 6, "d": {"requestType": request_type, "requestId": request_id}}
        if request_data is not None:
            message["d"]["requestData"] = request_data
        self.socket.send(json.dumps(message))
        while True:
            response = json.loads(self.socket.recv())
            if response.get("op") == 7 and response.get("d", {}).get("requestId") == request_id:
                data = response["d"]
                if not data.get("requestStatus", {}).get("result"):
                    raise OBSError(data["requestStatus"].get("comment", "OBS request failed"))
                return data.get("responseData", {})

    def start_recording(self) -> None:
        self.request("StartRecord")

    def stop_recording(self) -> Path:
        data = self.request("StopRecord")
        output_path = data.get("outputPath")
        if not output_path:
            raise OBSError("OBSから録画ファイルの場所を取得できません")
        return Path(output_path)

    def close(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None
