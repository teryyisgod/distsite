# 配布サイト 雛形

## ローカルで動かす
```
pip install -r requirements.txt
python app.py
```
→ http://127.0.0.1:5000 にアクセス

## ファイルを配布する
`uploads/` フォルダに配布したいファイルを置くだけでOK。
ログインしたユーザーだけがダウンロードページから取得できる。

## 無料でネット公開する(Render)
1. GitHubにこのフォルダをpush
2. https://render.com で「New Web Service」→ 該当リポジトリを選択
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app`
5. 環境変数 `SECRET_KEY` にランダムな文字列を設定(必須)
6. デプロイ完了後、発行されたURLでアクセス可能

## 注意点
- SQLiteはRenderの無料枠だと再デプロイ時にリセットされる可能性あり。
  ユーザーデータを保持したいなら無料枠のPostgreSQLに切り替えるのが安全。
- 本番運用するなら SECRET_KEY は必ず環境変数から読む(コード直書き厳禁)。
- パスワードは werkzeug の generate_password_hash でハッシュ化済み、平文保存はしていない。
