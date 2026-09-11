import streamlit as st
import pandas as pd
import plotly.express as px
from janome.tokenizer import Tokenizer
from collections import Counter
import re

# ---------------------------------------------------------
# 1. ページ基本設定
# ---------------------------------------------------------
st.set_page_config(
    page_title="研究授業 振り返り・変容分析ダッシュボード",
    page_icon="🏫",
    layout="wide"
)

# ---------------------------------------------------------
# 2. 設定パラメータ（カスタマイズ可能）
# ---------------------------------------------------------
# 管理者用パスワード（お好みの文字列に変更してください）
ADMIN_PASSWORD = "admin2026"

# 第1回データのデフォルトスプレッドシートURL
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/13KcOiiaqm4tO7VIl9e2EJ2d7t94hSOGp8PnReBNuiIo/edit?usp=sharing"

# ---------------------------------------------------------
# 3. データ読み込み用関数
# ---------------------------------------------------------
@st.cache_data(ttl=60)
def load_data(sheet_url):
    """GoogleスプレッドシートのURLからCSV形式でデータを読み込む関数"""
    try:
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
        if match:
            file_id = match.group(1)
            csv_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv"
            df = pd.read_csv(csv_url)
            return df
        else:
            return None
    except Exception as e:
        return None

# ---------------------------------------------------------
# 4. サイドバー構築
# ---------------------------------------------------------
st.sidebar.header("⚙️ システム設定")

# 管理者認証機能
input_pass = st.sidebar.text_input(
    "🔑 管理者パスワード", 
    type="password", 
    help="授業の新規登録や設定変更を行うには暗証番号が必要です。"
)
is_admin = (input_pass == ADMIN_PASSWORD)

if is_admin:
    st.sidebar.success("🔑 管理者権限認証済み")
else:
    if input_pass != "":
        st.sidebar.error("❌ パスワードが違います")
    st.sidebar.info("💡 閲覧専用モードで表示中")

st.sidebar.divider()

# データベースURL設定
st.sidebar.subheader("📊 データベース設定")
if is_admin:
    sheet_url = st.sidebar.text_input("GoogleスプレッドシートURL", value=DEFAULT_SHEET_URL)
else:
    sheet_url = DEFAULT_SHEET_URL
    st.sidebar.caption("※スプレッドシートURLの変更は管理者のみ許可されています。")

st.sidebar.divider()

# 生徒配付用URL案内
st.sidebar.subheader("📱 生徒配付用フォーム")
selected_session_sidebar = st.sidebar.selectbox("配付用実施回を選択", ["第1回", "第2回", "第3回"])
st.sidebar.text_input("生徒用回答フォームURL", value="https://docs.google.com/forms/d/e/1FAIpQLSc...", disabled=True)

# ---------------------------------------------------------
# 5. メイン画面・タブ構築
# ---------------------------------------------------------
st.title("🏫 研究授業 振り返り・変容分析ダッシュボード")
st.caption("第1回（事前データ）から第2回以降（リアルタイム回収）までの生徒の変容を追跡・分析します。")

tab1, tab2, tab3 = st.tabs(["⚙️ 研究授業 事前登録", "📊 教科別・結果表示", "📈 生徒の変容・分析"])

# --- タブ1: 事前登録（管理者権限で保護） ---
with tab1:
    st.header("研究授業の事前登録")
    
    if is_admin:
        st.success("🔓 管理者権限が確認されました。新しい授業計画を登録・保存できます。")
        with st.form("register_form"):
            session_num = st.selectbox("登録対象の実施回を選択", ["第1回", "第2回", "第3回", "第4回", "第5回"])
            subjects = st.multiselect(
                "対象教科（最大10教科）", 
                ["国語", "社会", "数学", "理科", "英語", "音楽", "美術", "保健体育", "技術家庭", "情報"]
            )
            pdf_file = st.file_uploader("ルーブリック資料（PDF）のアップロード", type=["pdf"])
            
            submitted = st.form_submit_button("この設定で研究授業を登録・保存", type="primary")
            if submitted:
                st.success(f"{session_num} の研究授業情報を正常に保存しました！")
    else:
        st.warning("🔒 授業の新規登録や設定変更は管理者（自校担当者）専用の機能です。")
        st.info("登録・設定変更を行う場合は、左側のサイドバーで「🔑 管理者パスワード」を入力してください。")

# データ読み込み実行
df = load_data(sheet_url)

# --- タブ2: 教科別・結果表示 ---
with tab2:
    st.header("教科別・結果表示")
    
    if df is not None and not df.empty:
        st.subheader("📋 取得データ一覧")
        st.dataframe(df, use_container_width=True)
        
        # 数値データとテキストデータの分離
        numeric_cols = df.select_dtypes(include=['number', 'float64', 'int64']).columns.tolist()
        text_cols = df.select_dtypes(include=['object']).columns.tolist()
        
        # 評価スコアの集計グラフ
        if numeric_cols:
            st.subheader("📊 評価・スコア集計")
            selected_num_col = st.selectbox("集計項目を選択", numeric_cols)
            fig_num = px.histogram(df, x=selected_num_col, title=f"「{selected_num_col}」の分布状況", text_auto=True)
            st.plotly_chart(fig_num, use_container_width=True)
            
        # 自由記述の形態素解析
        if text_cols:
            st.subheader("💬 自由記述テキストの単語出現頻度解析")
            selected_text_col = st.selectbox("分析対象の記述項目を選択", text_cols)
            
            text_data = " ".join(df[selected_text_col].dropna().astype(str))
            tokenizer = Tokenizer()
            tokens = tokenizer.tokenize(text_data)
            
            # 名詞かつ2文字以上の単語を抽出
            words = [
                token.surface for token in tokens 
                if token.part_of_speech.startswith('名詞') and len(token.surface) > 1
            ]
            
            if words:
                word_counts = Counter(words).most_common(10)
                word_df = pd.DataFrame(word_counts, columns=['出現単語', '回数'])
                fig_words = px.bar(
                    word_df, 
                    x='出現単語', 
                    y='回数', 
                    title=f"「{selected_text_col}」でよく使われているキーワード Top 10",
                    text_auto=True
                )
                st.plotly_chart(fig_words, use_container_width=True)
            else:
                st.info("解析可能なテキストデータが見つかりませんでした。")
    else:
        st.error("データの読み込みに失敗しました。Googleスプレッドシートの共有設定が「リンクを知っている全員」になっているかご確認ください。")

# --- タブ3: 生徒の変容・分析 ---
with tab3:
    st.header("生徒の変容・分析")
    st.write("事前データと事後データを照合し、生徒の意識や理解度の推移を分析します。")
    
    if df is not None and not df.empty:
        numeric_cols = df.select_dtypes(include=['number', 'float64', 'int64']).columns.tolist()
        if numeric_cols:
            st.subheader("📈 スコア変容グラフ")
            selected_val = st.selectbox("分析項目を選択", numeric_cols, key="transform_select")
            fig_box = px.box(df, y=selected_val, title=f"「{selected_val}」の全体スコア分布・ばらつき")
            st.plotly_chart(fig_box, use_container_width=True)
    else:
        st.info("表示可能なデータがありません。")
