import os
import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from io import StringIO
import logging
import pytz
import matplotlib.pyplot as plt
import japanize_matplotlib
import numpy as np

# ログ設定
logging.basicConfig(filename='script.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# 都道府県名をローマ字に変換する辞書
PREFECTURE_TO_ROMAJI = {
    "北海道": "hokkaido",
    "青森県": "aomori",
    "岩手県": "iwate",
    "宮城県": "miyagi",
    "秋田県": "akita",
    "山形県": "yamagata",
    "福島県": "fukushima",
    "茨城県": "ibaraki",
    "栃木県": "tochigi",
    "群馬県": "gunma",
    "埼玉県": "saitama",
    "千葉県": "chiba",
    "東京都": "tokyo",
    "神奈川県": "kanagawa",
    "新潟県": "niigata",
    "富山県": "toyama",
    "石川県": "ishikawa",
    "福井県": "fukui",
    "山梨県": "yamanashi",
    "長野県": "nagano",
    "岐阜県": "gifu",
    "静岡県": "shizuoka",
    "愛知県": "aichi",
    "三重県": "mie",
    "滋賀県": "shiga",
    "京都府": "kyoto",
    "大阪府": "osaka",
    "兵庫県": "hyogo",
    "奈良県": "nara",
    "和歌山県": "wakayama",
    "鳥取県": "tottori",
    "島根県": "shimane",
    "岡山県": "okayama",
    "広島県": "hiroshima",
    "山口県": "yamaguchi",
    "徳島県": "tokushima",
    "香川県": "kagawa",
    "愛媛県": "ehime",
    "高知県": "kochi",
    "福岡県": "fukuoka",
    "佐賀県": "saga",
    "長崎県": "nagasaki",
    "熊本県": "kumamoto",
    "大分県": "oita",
    "宮崎県": "miyazaki",
    "鹿児島県": "kagoshima",
    "沖縄県": "okinawa"
}

# ファイルパス
REF_FILE = "assets/ref_data.csv"
JS_OUTPUT_FILE = "rs_virus_data.js"
GRAPH_OUTPUT_FILE = "rs_virus_national_trend_adjusted.png"
CSV_FILE = "assets/rs_national_data.csv"

# 期間計算関数
def calculate_period(year, week):
    first_day_of_year = datetime.date(year, 1, 1)
    first_week_monday = first_day_of_year - datetime.timedelta(days=first_day_of_year.weekday())
    target_week_monday = first_week_monday + datetime.timedelta(weeks=week - 1)
    start_date = target_week_monday
    end_date = start_date + datetime.timedelta(days=6)
    return f"{start_date.year}年{start_date.month:02d}月{start_date.day:02d}日～{end_date.month:02d}月{end_date.day:02d}日"

# NIIDページからCSVリンクを取得し、JSファイルを生成
def fetch_and_generate_js():
    base_page_url = "https://www.niid.go.jp/niid/ja/data.html"
    response = requests.get(base_page_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    csv_url = None
    week = None
    year = None

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "teiten.csv" in href:
            csv_url = f"https://www.niid.go.jp{href}"
            year = int(href.split("/")[-1].split("-")[0])
            week = int(href.split("/")[-1].split("-")[1])
            break

    if not csv_url or not week or not year:
        raise ValueError("CSVリンクまたは週番号が取得できませんでした。")

    # CSVデータの取得
    response = requests.get(csv_url)
    response.raise_for_status()
    response.encoding = 'shift_jis'
    csv_data = StringIO(response.text)
    df = pd.read_csv(csv_data, skiprows=3)

    # 標準データの読み込み
    ref_data = pd.read_csv(REF_FILE)
    ref_data.columns = ref_data.columns.str.strip()
    ref_data.set_index("都道府県", inplace=True)

    # 必要な情報を抽出
    rs_prefList = []
    for i, row in df.iterrows():
        if pd.isna(row[0]) or not isinstance(row[0], str):
            continue
        if row[0] == "総数":
            continue

        # 標準値の取得
        standard = ref_data.loc[row[0], "定点当たり報告数"] if row[0] in ref_data.index else ""

        rs_prefList.append({
            "name": row[0],
            "id": PREFECTURE_TO_ROMAJI.get(row[0], row[0].lower().replace(" ", "_")),
            "standard": str(standard),
            "infectedperson": str(row[3]) if not pd.isna(row[3]) else "0",
            "fixedpoint": str(row[4]) if not pd.isna(row[4]) else "0.0",
            "subPeriod": "",
            "subWeek": ""
        })

    # 全国データを追加
    rs_prefList.insert(0, {
        "name": "全国",
        "id": "nationwide",
        "standard": "",
        "infectedperson": str(df.iloc[0, 3]) if not pd.isna(df.iloc[0, 3]) else "0",
        "fixedpoint": str(df.iloc[0, 4]) if not pd.isna(df.iloc[0, 4]) else "0.0",
        "subPeriod": "",
        "subWeek": ""
    })

    # JSONデータ生成
    rs_status = {
        "week": week,
        "totalization": f"{year}年{week}週",
        "period": calculate_period(year, week),
        "timestamp": int(datetime.datetime.now().timestamp())
    }

    js_output = f"var rs_status = {json.dumps(rs_status, ensure_ascii=False, indent=4)};\n"
    js_output += f"var rs_prefList = {json.dumps(rs_prefList, ensure_ascii=False, indent=4)};\n"

    # JavaScriptファイルに書き込み
    with open(JS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(js_output)
    print(f"JavaScriptデータが生成されました: {JS_OUTPUT_FILE}")

# グラフ生成
def generate_graph():
    if not os.path.exists(JS_OUTPUT_FILE):
        raise RuntimeError(f"{JS_OUTPUT_FILE} が見つかりません。先に生成してください。")

    # JavaScriptファイルから現在の週を取得
    with open(JS_OUTPUT_FILE, "r", encoding="utf-8") as f:
        js_data = f.read()
        start_index = js_data.find("var rs_status = {") + len("var rs_status = ")
        end_index = js_data.find("};", start_index) + 1
        rs_status = json.loads(js_data[start_index:end_index])
        current_week = rs_status["week"]

    # CSVファイルを読み込み
    df = pd.read_csv(CSV_FILE)
    df = df.rename(columns=lambda x: x.strip()).replace({None: np.nan, "-": np.nan})

    # 特定の範囲をNaNにする
    df.loc[0:7, "2018年"] = np.nan
    if "2024年" in df.columns:
        df.loc[current_week:, "2024年"] = np.nan

    # グラフ生成
    fig, ax = plt.subplots(figsize=(14, 8))
    for year in df.columns[1:]:
        values = df[year].astype(float)
        ax.plot(df.iloc[:, 0], values, label=year, marker="o")

    ax.set_title("全国のRSウイルス流行期 定点あたり報告数", pad=30)
    ax.set_ylabel("\n".join("定点あたり報告数"), labelpad=20, rotation=0, va="center", ha="center")
    ax.grid(axis="y", linestyle=":", linewidth=0.80)
    ax.grid(axis="y", linestyle=":", linewidth=0.8, color="gray")
    ax.set_ylim(0, 7)
    ax.set_yticks(np.arange(0, 8, 1))

    # 凡例の設定
    ax.legend(
        loc="upper center",
        fontsize=10,
        bbox_to_anchor=(0.5, 1.065),
        ncol=len(df.columns[1:]),
        frameon=False
    )

    # X軸のカスタムラベル
    ax.set_xticks(np.arange(1, 54, 3))
    ax.set_xticklabels([f"{i}週" for i in range(1, 54, 3)], fontsize=10)
    ax.tick_params(axis="x", which="both", pad=5)

    # 月ラベル用の背景
    background_rect = plt.Rectangle(
        (ax.get_position().x0, ax.get_position().y0 - 0.1),
        ax.get_position().width, 0.05,
        transform=fig.transFigure,
        color="lightyellow",
        alpha=0.5,
        zorder=1
    )
    fig.patches.append(background_rect)

    # 月ラベルの追加
    months = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
    month_positions = np.linspace(1, 53, len(months))

    for pos, month in zip(month_positions, months):
        ax.text(
            pos,
            -0.11,
            month,
            ha="center",
            va="center",
            fontsize=10,
            transform=ax.get_xaxis_transform(),
            zorder=3
        )

    # 横軸タイトルを非表示
    ax.set_xlabel("")

    # グラフを保存
    plt.savefig(GRAPH_OUTPUT_FILE, bbox_inches="tight", dpi=300)
    plt.show()
    print(f"グラフが生成されました: {GRAPH_OUTPUT_FILE}")

# 実行フロー
if __name__ == "__main__":
    fetch_and_generate_js()
    generate_graph()
