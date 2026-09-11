import streamlit as st
import pandas as pd
import plotly.express as px
from janome.tokenizer import Tokenizer
from pypdf import PdfReader
from streamlit_gsheets import GSheetsConnection
import json
import os
import urllib.parse

# ---------------------------------------------------------
# 1. ページ基本設定
# ---------------------------------------------------------
st.set_page_config(page_title="研究授業 振り返り・変容分析ダッシュボード", layout="wide")
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

st.title("🏫 研究授業 振り返り・変容分析ダッシュボード")
st.caption("第1回（事前データ）から第2回以降（リアルタイム回収）までの生徒の変容を追跡・分析します。")

# ---------------------------------------------------------
# 2. 基本設定パラメータ（パスワード・初期URL）
# ---------------------------------------------------------
# 管理者用パスワード
ADMIN_PASSWORD = "admin2026"

# 第1回データおよび標準回答用スプレッドシートURL
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/13KcOiiaqm4tO7VIl9e2EJ2d7t94hSOGp8PnReBNuiIo/edit?usp=sharing"

# Googleフォーム自動配付用設定
FORM_ID = "YOUR_FORM_ID_HERE"  # 例: 1FAIpQLSc... のようなフォームID
ENTRY_ID_ROUND = "entry.123456789"  # 「実施回」質問項目のエントリーID

# ---------------------------------------------------------
# 3. 事前登録データの保存・読み込み処理
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "lesson_settings.json")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False

if "lesson_settings" not in st.session_state:
    st.session_state["lesson_settings"] = load_settings()

# ---------------------------------------------------------
# 4. サイドバー設定（管理者認証 ＆ データベース ＆ QRコード生成）
# ---------------------------------------------------------
st.sidebar.header("🔑 システム認証")
input_pass = st.sidebar.text_input(
    "管理者パスワード", 
    type="password", 
    help="登録や設定更新を行う場合は管理者パスワードを入力してください。"
)
is_admin = (input_pass == ADMIN_PASSWORD)

if is_admin:
    st.sidebar.success("🔑 管理者権限認証済み")
else:
    if input_pass != "":
        st.sidebar.error("❌ パスワードが違います")
    st.sidebar.info("💡 閲覧モードで表示中")

st.sidebar.divider()
st.sidebar.header("⚙️ データベース設定")

if is_admin:
    spreadsheet_url = st.sidebar.text_input(
        "Googleフォーム回答スプレッドシートのURLを入力",
        value=DEFAULT_SHEET_URL,
        help="Googleフォームの回答が蓄積されるスプレッドシートのURLを貼り付けてください"
    )
else:
    spreadsheet_url = DEFAULT_SHEET_URL
    st.sidebar.caption("※スプレッドシートURLの変更は管理者のみ可能です。")

# --- 誤配付防止：生徒向けURL・QRコード自動生成 ---
st.sidebar.divider()
st.sidebar.header("📱 生徒配付用URL・QRコード生成")
target_round_for_qr = st.sidebar.selectbox(
    "配付したい実施回を選択",
    [f"第{i}回" for i in range(2, 11)],
    key="qr_round_select"
)

if FORM_ID != "YOUR_FORM_ID_HERE":
    encoded_round = urllib.parse.quote(target_round_for_qr)
    generated_form_url = f"https://docs.google.com/forms/d/e/{FORM_ID}/viewform?usp=pp_url&{ENTRY_ID_ROUND}={encoded_round}"
    
    st.sidebar.success(f"【{target_round_for_qr}】専用フォーム準備完了")
    st.sidebar.text_input("生徒配付用URL（選択済）", value=generated_form_url, key="generated_url_input")
    
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={urllib.parse.quote(generated_form_url)}"
    st.sidebar.image(qr_api_url, caption=f"{target_round_for_qr} 配付用QRコード")
else:
    st.sidebar.warning("⚠️ フォームIDが未設定です。コード内の FORM_ID を設定してください。")

# ---------------------------------------------------------
# 5. データベース接続・データ統合処理
# ---------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_data(url):
    if not url:
        return pd.DataFrame(columns=["回", "教科", "事前意見あり", "新たな気づき", "学び合い内容", "わかったこと"])
    try:
        clean_url = url.strip()
        data = conn.read(spreadsheet=clean_url, worksheet=0)
        
        column_mapping = {
            "実施回": "回",
            "1. 教科名": "教科",
            "2. 学び合いの前に自分の意見をもつことができましたか": "事前意見あり",
            "3. 学び合いでは新たな考えや疑問が生まれましたか": "新たな気づき",
            "4. 仲間との学び合いではどのような学び合いをしましたか": "学び合い内容",
            "5. 今日の授業でわかったことや大切だと感じたことは何ですか": "わかったこと"
        }
        data = data.rename(columns=column_mapping)
        return data
    except Exception as e:
        st.error(f"データの読み込みに失敗しました。URLを確認してください: {e}")
        return pd.DataFrame(columns=["回", "教科", "事前意見あり", "新たな気づき", "学び合い内容", "わかったこと"])

survey_df = load_data(spreadsheet_url)

# データ管理・第1回統合 & 引き継ぎガイドボタン
st.sidebar.divider()
st.sidebar.subheader("📁 データ管理")

include_1st = st.sidebar.checkbox("第1回データ（ベースライン）を含めて変容を分析する", value=True)

if include_1st:
    try:
        sheet_id = "13KcOiiaqm4tO7VIl9e2EJ2d7t94hSOGp8PnReBNuiIo"
        url_1st = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        df_1st = pd.read_csv(url_1st)
        
        df_processed = pd.DataFrame()
        df_processed["回"] = ["第1回"] * len(df_1st)
        df_processed["教科"] = "全般"
        df_processed["事前意見あり"] = None
        df_processed["新たな気づき"] = None
        
        col_learning = [c for c in df_1st.columns if "学び合い" in c]
        if col_learning:
            df_processed["学び合い内容"] = df_1st[col_learning[0]].fillna("").astype(str)
        else:
            df_processed["学び合い内容"] = ""
            
        df_processed["わかったこと"] = ""

        survey_df = pd.concat([df_processed, survey_df], ignore_index=True)
        st.sidebar.success("第1回データを統合表示中")
    except Exception as e:
        st.sidebar.error(f"第1回データ読み込みエラー: {e}")

# 引き継ぎガイドボタン
with st.sidebar.popover("🔰 パソコンが苦手な方向け：引き継ぎ・復元ガイド", use_container_width=True):
    st.markdown("### 🏫 Googleドライブへのバックアップ＆引き継ぎ手順")
    st.info("この案内通りに進めるだけで、パソコンの交換や異動時のデータ保存・復元が完了します！")
    
    tab_guide1, tab_guide2 = st.tabs(["📤 1. データ保存（異動前）", "📥 2. データ復元（異動後）"])
    
    with tab_guide1:
        st.markdown("**【ステップ 1】 設定ファイルをダウンロードする**")
        json_str = json.dumps(st.session_state["lesson_settings"], ensure_ascii=False, indent=4)
        st.download_button(
            label="1. ここをクリックして設定ファイルを保存",
            data=json_str,
            file_name="lesson_settings.json",
            mime="application/json",
            type="primary",
            use_container_width=True
        )
        st.markdown("**【ステップ 2】 Googleドライブに保存する**")
        st.write("1. Web版Googleドライブを開きます。")
        st.write("2. 「研究授業ダッシュボード」という名前の新規フォルダーを作成します。")
        st.write("3. そのフォルダーの中に `lesson_settings.json` と `dashboard.py` を保存します。")

    with tab_guide2:
        st.markdown("**【ステップ 1】 Googleドライブから取り出す**")
        st.write("1. 新しいパソコンでGoogleドライブから2つのファイルをダウンロードします。")
        st.markdown("**【ステップ 2】 設定ファイルを画面から復元する**")
        uploaded_json = st.file_uploader("保存した lesson_settings.json をここにドラッグ", type=["json"], key="guide_restore")
        if uploaded_json is not None:
            try:
                loaded_data = json.load(uploaded_json)
                st.session_state["lesson_settings"] = loaded_data
                save_settings(loaded_data)
                st.balloons()
                st.success("🎉 設定が完全に復元されました！")
            except Exception as e:
                st.error(f"復元エラーが発生しました: {e}")

# ---------------------------------------------------------
# 6. メイン画面（3タブ構造）
# ---------------------------------------------------------
tab_register, tab1, tab2 = st.tabs(["⚙️ 研究授業 事前登録", "📊 教科別・結果表示", "📈 生徒の変容・分析"])

# ==========================================
# タブ0: 研究授業 事前登録
# ==========================================
with tab_register:
    st.header("研究授業の事前登録")
    st.caption("実施される研究授業の回、対象教科（最大10教科）、および各教科のルーブリックPDFを事前登録します。")

    if is_admin:
        st.success("🔓 管理者権限が確認されました。授業計画の登録・編集が可能です。")
        reg_round = st.selectbox("登録対象の実施回を選択", [f"第{i}回" for i in range(2, 11)])
        all_subject_options = ["国語", "社会", "数学", "理科", "英語", "保体", "技家", "美術", "音楽", "総合"]
        
        current_reg = st.session_state["lesson_settings"].get(reg_round, {})
        default_subs = current_reg.get("subjects", [])
        
        selected_subjects = st.multiselect(
            f"【{reg_round}】で実施する教科を選択してください（最大10教科）",
            options=all_subject_options,
            default=[s for s in default_subs if s in all_subject_options],
            max_selections=10
        )
        
        rubric_inputs = current_reg.get("rubrics", {})
        if selected_subjects:
            st.subheader("各教科のルーブリックPDFアップロード")
            for sub in selected_subjects:
                has_rubric = sub in rubric_inputs and rubric_inputs[sub]
                status_msg = " (登録済み文章あり)" if has_rubric else ""
                uploaded_pdf = st.file_uploader(f"📄 {sub} のルーブリックPDF{status_msg}", type=["pdf"], key=f"{reg_round}_{sub}")
                
                if uploaded_pdf:
                    reader = PdfReader(uploaded_pdf)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    rubric_inputs[sub] = text

        if st.button("この設定で研究授業を登録・保存する", type="primary"):
            if not selected_subjects:
                st.warning("教科が一つも選択されていません。")
            else:
                updated_rubrics = {sub: rubric_inputs.get(sub, "") for sub in selected_subjects}
                st.session_state["lesson_settings"][reg_round] = {
                    "subjects": selected_subjects,
                    "rubrics": updated_rubrics
                }
                if save_settings(st.session_state["lesson_settings"]):
                    st.success(f"🎉 {reg_round} の授業設定を保存しました！")
    else:
        st.warning("🔒 授業計画の新規登録や編集を行うには、サイドバーで管理者パスワードを入力してください。")

# ==========================================
# タブ1: 教科別・結果表示
# ==========================================
with tab1:
    st.header("教科別・回別 集計結果")
    st.caption("事前登録された教科とルーブリックに基づいて、授業ごとの回答を確認します。")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        available_rounds = [r for r in survey_df["回"].unique() if r != "第1回"]
        selected_round = st.selectbox("実施回を選択", ["すべて"] + available_rounds if available_rounds else ["データなし"])
    
    registered_data = st.session_state["lesson_settings"].get(selected_round, {})
    registered_subs = registered_data.get("subjects", [])
    
    with col_f2:
        if registered_subs:
            st.info(f"💡 {selected_round} に登録済みの教科を表示中")
            selected_subject = st.selectbox("教科を選択", ["すべて"] + registered_subs)
        else:
            available_subjects = [s for s in survey_df["教科"].unique() if s != "全般"]
            selected_subject = st.selectbox("教科を選択（未登録のため全表示）", ["すべて"] + available_subjects if available_subjects else ["データなし"])
    
    filtered_df = survey_df[survey_df["回"] != "第1回"].copy()
    if selected_round != "すべて" and selected_round != "データなし":
        filtered_df = filtered_df[filtered_df["回"] == selected_round]
    if selected_subject != "すべて" and selected_subject != "データなし":
        filtered_df = filtered_df[filtered_df["教科"] == selected_subject]
        
    if filtered_df.empty:
        st.info("該当する授業データがまだありません。")
    else:
        st.markdown(f"### 対象データ件数: {len(filtered_df)} 件")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### Q2. 学び合い前の意見保持")
            fig2 = px.pie(filtered_df.dropna(subset=["事前意見あり"]), names="事前意見あり", color="事前意見あり",
                         color_discrete_map={"もつことができた":"#2E7D32", "もつことができなかった":"#C62828"})
            st.plotly_chart(fig2, use_container_width=True)
            
        with col2:
            st.markdown("##### Q3. 新たな考え・疑問の発生")
            fig3 = px.pie(filtered_df.dropna(subset=["新たな気づき"]), names="新たな気づき")
            st.plotly_chart(fig3, use_container_width=True)
            
        st.subheader("📝 生徒の記述回答一覧")
        st.dataframe(filtered_df[["回", "教科", "学び合い内容", "わかったこと"]], use_container_width=True)

    rubrics_dict = registered_data.get("rubrics", {})
    if selected_subject in rubrics_dict and rubrics_dict[selected_subject]:
        st.divider()
        st.subheader(f"📋 【{selected_subject}】 の登録ルーブリック")
        with st.expander("ルーブリック本文を表示"):
            st.write(rubrics_dict[selected_subject])

# ==========================================
# タブ2: 生徒の変容・分析
# ==========================================
with tab2:
    st.header("生徒の変容追跡・テキスト分析")
    st.caption("第1回の記述（事前学習）を起点として、回を追うごとの「学び合いの質の変化」を分析します。")
    
    if survey_df.empty:
        st.info("分析対象のデータがありません。")
    else:
        st.subheader("1. 意識の変容推移（第2回以降）")
        df_change = survey_df.dropna(subset=["事前意見あり"])
        if not df_change.empty:
            summary_df = df_change.groupby(["回", "事前意見あり"]).size().reset_index(name="人数")
            fig_bar = px.bar(summary_df, x="回", y="人数", color="事前意見あり", barmode="group",
                             title="「学び合い前に自分の意見を持てたか」の推移",
                             color_discrete_map={"もつことができた":"#2E7D32", "もつことができなかった":"#C62828"})
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.write("※意識推移グラフは第2回以降の回答が集まることで表示されます。")
        
        st.divider()
        st.subheader("2. 「学び合いの内容」主要キーワードの変容（第1回 vs 第2回以降）")
        
        def extract_words(text_series):
            t = Tokenizer()
            words = []
            for text in text_series.dropna():
                tokens = t.tokenize(str(text))
                for token in tokens:
                    pos = token.part_of_speech.split(',')[0]
                    if pos in ['名詞', '動詞', '形容詞'] and len(token.surface) > 1:
                        words.append(token.base_form)
            return words

        all_rounds = sorted(survey_df["回"].unique())
        cols = st.columns(min(len(all_rounds), 3))
        for idx, r in enumerate(all_rounds):
            round_texts = survey_df[survey_df["回"] == r]["学び合い内容"]
            words = extract_words(round_texts)
            
            with cols[idx % 3]:
                st.markdown(f"#### 📍 {r}")
                if words:
                    word_counts = pd.Series(words).value_counts().head(8).reset_index()
                    word_counts.columns = ["キーワード", "出現回数"]
                    fig_word = px.bar(word_counts, x="出現回数", y="キーワード", orientation='h',
                                      title=f"{r} の特徴的ワード Top 8")
                    fig_word.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig_word, use_container_width=True)
                else:
                    st.write("記述データがありません。")
