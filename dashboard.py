import streamlit as st
import pandas as pd
import plotly.express as px
from janome.tokenizer import Tokenizer
from pypdf import PdfReader
from streamlit_gsheets import GSheetsConnection
import json
import os
import urllib.parse
import re

# ---------------------------------------------------------
# 1. ページ基本設定
# ---------------------------------------------------------
st.set_page_config(page_title="研究授業 振り返り・変容分析ダッシュボード", layout="wide")
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

st.title("🏫 研究授業 振り返り・変容分析ダッシュボード")
st.caption("第1回（事前データ）から第2回以降（リアルタイム回収）までの生徒の変容を追跡・分析します。")

# ---------------------------------------------------------
# 2. 基本設定パラメータ
# ---------------------------------------------------------
ADMIN_PASSWORD = "admin2026"
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PySOCYKAIg0r_apzPgLRuaayEpNa0dlFDY95PGccfk0/edit?usp=sharing"

FORM_ID = "1FAIpQLSe0E6C8Q3eqMsW_WLXRN6vYAFJn97RoqixZuJrXiDh4FsFThA"
ENTRY_ID_ROUND = "entry.999413418"

# ---------------------------------------------------------
# 3. 事前登録データの保存・永続化処理
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "lesson_settings.json")

DEFAULT_SETTINGS = {
    "第2回": {
        "subjects": ["社会", "数学", "理科", "技家", "保体", "英語"],
        "rubrics": {}
    }
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return data
        except Exception:
            pass
    return DEFAULT_SETTINGS

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
# 4. サイドバー設定
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
        help="Googleフォームの回答が蓄積されるスプレッドシートのURLを入力"
    )
else:
    spreadsheet_url = DEFAULT_SHEET_URL
    st.sidebar.caption("※スプレッドシートURLの変更は管理者のみ可能です。")

# 【追加】古いデータを消去してスプレッドシートの最新状態を取得するボタン
if st.sidebar.button("🔄 データを最新状態に更新"):
    st.cache_data.clear()
    st.rerun()

# 生徒配付用URL・QRコード生成
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
    st.sidebar.warning("⚠️ フォームIDが未設定です。")

# ---------------------------------------------------------
# 5. データベース接続・データ読み込み（リアルタイム取得版）
# ---------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

# ttl=0 に変更し、過去の古いデータを保持せず毎回スプレッドシートから直接取得します
@st.cache_data(ttl=0)
def load_data(url):
    if not url:
        return pd.DataFrame(columns=["回", "教科", "事前意見あり", "新たな気づき", "学び合い内容", "わかったこと"])
    try:
        clean_url = url.strip()
        data = conn.read(spreadsheet=clean_url, worksheet=0)
        
        data.columns = [str(col).strip() for col in data.columns]
        
        rename_dict = {}
        for col in data.columns:
            if "実施回" in col:
                rename_dict[col] = "回"
            elif "教科" in col:
                rename_dict[col] = "教科"
            elif "事前" in col or "自分" in col or col.startswith("2."):
                rename_dict[col] = "事前意見あり"
            elif "新" in col or col.startswith("3."):
                rename_dict[col] = "新たな気づき"
            elif "仲間" in col or "どのような学び合い" in col or col.startswith("4."):
                rename_dict[col] = "学び合い内容"
            elif "わかった" in col or "大切" in col or col.startswith("5."):
                rename_dict[col] = "わかったこと"
                
        data = data.rename(columns=rename_dict)
        
        if "回" in data.columns:
            data = data.dropna(subset=["回"])
            
            # 入力形式の統一処理（数字のみなどの場合に「第N回」の形に整形）
            def normalize_round(val):
                val_str = str(val).strip()
                match = re.search(r'(\d+)', val_str)
                if match:
                    return f"第{match.group(1)}回"
                return val_str
            
            data["回"] = data["回"].apply(normalize_round)
            
        return data
    except Exception as e:
        st.warning(f"データ読み込み待機中... ({e})")
        return pd.DataFrame(columns=["回", "教科", "事前意見あり", "新たな気づき", "学び合い内容", "わかったこと"])

survey_df = load_data(spreadsheet_url)

# 第1回データの統合処理
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
    except Exception:
        pass

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
                save_settings(st.session_state["lesson_settings"])
                st.success(f"🎉 {reg_round} の授業設定を保存しました！")
    else:
        st.warning("🔒 授業計画の新規登録や編集を行うには、サイドバーで管理者パスワードを入力してください。")

# ==========================================
# タブ1: 教科別・結果表示
# ==========================================
with tab1:
    st.header("教科別・回別 集計結果")
    st.caption("事前登録された教科とルーブリックに基づいて、授業ごとの回答を確認します。")
    
    filtered_df = survey_df[~survey_df["回"].astype(str).str.contains("第1回")].copy()
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        available_rounds = sorted([str(r).strip() for r in filtered_df["回"].dropna().unique() if str(r).strip() != ""])
        if available_rounds:
            selected_round = st.selectbox("実施回を選択", ["すべて"] + available_rounds)
        else:
            selected_round = "データなし"
            st.selectbox("実施回を選択", ["データなし"], disabled=True)
    
    registered_data = st.session_state["lesson_settings"].get(selected_round, {})
    registered_subs = registered_data.get("subjects", [])
    
    with col_f2:
        if registered_subs:
            st.info(f"💡 {selected_round} に登録済みの教科を表示中")
            selected_subject = st.selectbox("教科を選択", ["すべて"] + registered_subs)
        else:
            available_subjects = [str(s) for s in filtered_df["教科"].dropna().unique() if str(s) != "全般"]
            if available_subjects and selected_round != "データなし":
                selected_subject = st.selectbox("教科を選択（全表示）", ["すべて"] + available_subjects)
            else:
                selected_subject = "データなし"
                st.selectbox("教科を選択", ["データなし"], disabled=True)
    
    if selected_round == "データなし":
        filtered_df = pd.DataFrame()
    else:
        if selected_round != "すべて":
            filtered_df = filtered_df[filtered_df["回"].astype(str) == selected_round]
        if selected_subject != "すべて" and selected_subject != "データなし":
            filtered_df = filtered_df[filtered_df["教科"].astype(str) == selected_subject]
        
    if filtered_df.empty:
        st.info("ℹ️ 該当する授業データがまだありません。")
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
        
        STOP_WORDS = {
            "こと", "できる", "意見", "ある", "考え", "自分", "わかる", "友達",
            "思う", "する", "いる", "なる", "いう", "ない", "それ", "これ",
            "ため", "もの", "そう", "よう", "人", "みんな", "授業", "今日",
            "今回", "ほう", "さん", "ちゃん", "なし", "ん", "グループ", "話し合い"
        }

        def extract_words(text_series):
            t = Tokenizer()
            words = []
            for text in text_series.dropna():
                tokens = t.tokenize(str(text))
                for token in tokens:
                    pos = token.part_of_speech.split(',')[0]
                    base = token.base_form
                    if pos in ['名詞', '動詞', '形容詞']:
                        if len(base) > 1 and base not in STOP_WORDS:
                            words.append(base)
            return words

        all_rounds = sorted([str(r) for r in survey_df["回"].dropna().unique() if str(r).startswith("第")])
        
        cols = st.columns(min(len(all_rounds), 3)) if all_rounds else []
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
