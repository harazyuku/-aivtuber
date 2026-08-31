# 自動AI VTuber

マイクを使わず、台本生成から音声付き動画の作成までを自動で行う別プロジェクトです。

## 現在できること

1. Geminiで30〜45秒の台本を生成
2. AivisSpeechで音声ファイルを生成
3. アバター画像と音声をFFmpegで縦動画に合成

## 準備

```bash
cp .env.example .env
```

`.env`にGemini APIキーを設定し、`assets/avatar.png`にアバター画像を置きます。AivisSpeechを起動してから実行してください。

```bash
python3 main.py
```

動画は`output/`に作成されます。

字幕は台本から自動生成し、動画に焼き込みます。無効にする場合は`.env`で`BURN_SUBTITLES=false`にします。Macでは字幕対応の`ffmpeg-full`を使用し、必要なら`FFMPEG_FULL_BIN`で実行ファイルの場所を指定してください。

## 全体設計

Pythonの`main.py`が全体の進行役になり、次の順番で処理します。

```text
Gemini（台本）
  → AivisSpeech（音声）
  → VTube Studio（モデル・口パク）
  → OBS（録画）
  → FFmpeg（音声と映像の合成）
  → YouTube Data API（投稿）
```

各処理の役割は分離しています。`vtube.py`はVTube Studio、`obs.py`はOBS、`youtube.py`はGoogle OAuth認証とYouTube投稿を担当します。`prompts/character.txt`は台本のキャラクター設定、`.env`はAPIキーや投稿設定を担当します。

## Live2D録画

OBSにVTube Studioのウィンドウキャプチャを1つ設定し、OBS WebSocketを有効にしてから、`.env`で`LIVE2D_RECORD=true`にします。OBSのWebSocket設定でパスワードを設定した場合は`OBS_PASSWORD`にも設定してください。

モデルの読み込み直後に描画が遅れる環境では、`VTS_MODEL_READY_DELAY`で録画開始前の待ち時間（秒）を調整できます。

VTube StudioのPlugin APIを許可すると、初回実行時に認証確認が表示されます。許可後はMayoiの読み込み、録画開始・停止、音声との合成を自動で行います。

生成した音声の音量を解析し、VTube Studioのカスタム入力パラメータ`AutoMouth`へ送るため、マイクなしで口パクします。初回だけMayoiのモデル設定で、口の開きのINPUTに`AutoMouth`を選んでください。モデルによって口パラメータ名が違う場合は`VTS_MOUTH_PARAMETER`を変更してください。

OBS録画開始とのタイミング差を補正するため、音声を`AUDIO_SYNC_DELAY`秒遅らせます。口がまだ遅れる場合は`.env`で`0.10`〜`0.25`の範囲に調整してください。

## 注意

## YouTube自動投稿

Google CloudでYouTube Data API v3を有効にし、デスクトップアプリ用OAuthクライアントを作成して`client_secrets.json`をプロジェクト直下に置きます。公式のOAuth方式で、初回だけブラウザの許可が必要です。

まずは非公開投稿で確認します。

```bash
pip install -r requirements.txt
UPLOAD_TO_YOUTUBE=true python3 main.py
```

初回認証後は`youtube_token.json`を使って自動投稿します。公開する場合は`.env`の`YOUTUBE_PRIVACY_STATUS=public`に変更してください。YouTube投稿には公式の`videos.insert`を使っています。

## 自動投稿の設計

### 実行方式

Macでは`launchd`（macOS標準のスケジュール機能）から、決めた時刻に次のコマンドを実行します。

```bash
UPLOAD_TO_YOUTUBE=true python3 main.py
```

このコマンド1回で、台本生成から動画作成、YouTube投稿までを行います。Linux Mintへ移す場合は、同じ処理を`systemd timer`または`cron`（Linuxの定期実行機能）から呼び出します。

### 起動前の条件

- VTube Studio、OBS、AivisSpeechが起動している
- OBS WebSocketが有効になっている
- `.env`に必要なAPIキーと接続先が設定されている
- Google OAuthの初回認証が完了し、`youtube_token.json`が存在する

### 投稿の安全策

- 初期値は`YOUTUBE_PRIVACY_STATUS=private`（非公開）
- `UPLOAD_TO_YOUTUBE=false`なら動画生成だけで止まり、投稿しない
- 台本生成、音声生成、録画、投稿のどこかで失敗した場合、その回は投稿しない
- 認証情報やAPIキーは`.gitignore`でGitに含めない
- 投稿先を公開にする場合だけ、`.env`を`YOUTUBE_PRIVACY_STATUS=public`へ変更する

### 将来の拡張

投稿済み動画のURLと実行結果をログに保存し、失敗時にメール通知する。さらに、重複投稿防止、投稿時間のランダム化、予約公開にも対応する。
