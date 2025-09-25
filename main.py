import discord
from groq import Groq
import os
from dotenv import load_dotenv
import asyncio

# .envファイルから環境変数を読み込む
load_dotenv()

# 複数のAPIキーをリストで取得し設定
GROQ_API_KEYS = [os.getenv('GROQ_API_KEY1'), os.getenv('GROQ_API_KEY2')]
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
KAZ_CONTEXT = os.getenv('KAZ_CONTEXT')
current_key_index = 0

# 必要なAPIキーが存在するか確認
if not all([GROQ_API_KEYS[0], DISCORD_TOKEN, KAZ_CONTEXT]):
    print("エラー: DISCORD_TOKEN または GROQ_API_KEY1 または KAZ_CONTEXT が設定されていません。")
    exit()

# Groqクライアントの初期化関数
def initialize_groq_client():
    global current_key_index
    api_key = GROQ_API_KEYS[current_key_index]
    return Groq(api_key=api_key)

groq_client = initialize_groq_client()
LLM_MODEL = "llama-3.1-8b-instant"

# Intentsの設定
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
client = discord.Client(intents=intents)

# メンション必須フラグ
MENTION_REQUIRED = False

# 過去の会話を取得し、Groq APIへのメッセージ形式に変換する関数
# ボットのスリープ後もDiscordの履歴から会話を取得
async def get_groq_messages(channel, current_prompt):
    # 直近8件のメッセージ履歴を取得（ユーザーとボットの会話4往復分を想定）
    # history()は最新のメッセージから取得される
    messages_history = [msg async for msg in channel.history(limit=8)]
    
    # 履歴を古い順に並び替え、システムプロンプトから始める
    messages_history.reverse()
    groq_messages = [{"role": "system", "content": KAZ_CONTEXT}]

    for msg in messages_history:
        # ユーザーがボットに返信を求めていないメッセージ（例: 他のユーザーの会話、コマンドなど）は除外
        if msg.author == client.user:
            groq_messages.append({"role": "assistant", "content": msg.content})
        else:
            # メンションは除いてクリーンなプロンプトを作成
            clean_content = msg.content.replace(f'<@!{client.user.id}>', '').replace(f'<@{client.user.id}>', '').strip()
            if clean_content:
                groq_messages.append({"role": "user", "content": clean_content})
            
    # 現在のユーザーのプロンプトを追加
    groq_messages.append({"role": "user", "content": current_prompt})

    return groq_messages

# Groq APIを利用して応答を生成する関数
async def generate_response(prompt, channel):
    global groq_client, current_key_index, GROQ_API_KEYS
    
    # 応答を生成するために必要なメッセージリストを取得
    messages_for_groq = await get_groq_messages(channel, prompt)

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=messages_for_groq,
            model=LLM_MODEL,
            temperature=0.7, 
        )
        return chat_completion.choices[0].message.content.strip()

    except Exception as e:
        print(f"Groq APIエラー: {e}")
        
        # エラー発生時にキーを切り替える
        if len(GROQ_API_KEYS) > 1:
            current_key_index = (current_key_index + 1) % len(GROQ_API_KEYS)
            print(f"APIキーを切り替えます。次のキーインデックス: {current_key_index}")
            groq_client = initialize_groq_client()
        
        # 切り替え後のAPIでもエラーが続くか、キーが1つしかない場合
        return "ごめん、ちょっと考え中..."

# ボット起動時の処理
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

# メッセージ受信時の処理
@client.event
async def on_message(message):
    # ボット自身のメッセージは無視
    if message.author == client.user:
        return

    if message.content == '!kaz_toggle_mention':
        global MENTION_REQUIRED
        MENTION_REQUIRED = not MENTION_REQUIRED
        status = "必須" if MENTION_REQUIRED else "不要"
        await message.channel.send(f"ボットの返信にメンションが**{status}**になりました。")
        return

    # メンションモードの確認
    should_respond = (not MENTION_REQUIRED) or client.user.mentioned_in(message)

    if should_respond:
        # メンションがあれば除去
        prompt = message.content.replace(f'<@!{client.user.id}>', '').replace(f'<@{client.user.id}>', '').strip()
        
        # 応答生成中の表示
        async with message.channel.typing():
            # Groq APIで応答を生成
            response = await generate_response(prompt, message.channel)
            await message.channel.send(response)

# ボットの実行
if __name__ == "__main__":
    if DISCORD_TOKEN:
        client.run(DISCORD_TOKEN)
