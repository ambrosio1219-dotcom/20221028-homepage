# -*- coding: utf-8 -*-
"""
기타 전시관 (Guitar Gallery) - 중간고사 과제
Flask + SQLite 로 만든 전시 형태의 홈페이지

실행 방법
    pip install flask
    python app.py
    브라우저에서 http://127.0.0.1:5000 접속
"""

import os
import sqlite3
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gallery.db")

app = Flask(__name__)
# 세션(로그인 상태)을 암호화하는 열쇠. 실제 서비스라면 외부에 노출하면 안 된다.
app.secret_key = "midterm-guitar-gallery-secret-key"


# ------------------------------------------------------------------
# 데이터베이스
# ------------------------------------------------------------------
def get_db():
    """요청 한 번에 연결 하나만 쓰도록 g 객체에 담아 둔다."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row      # 컬럼 이름으로 꺼내 쓰기 위해
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """표가 없으면 만들고, 전시할 기타 자료가 비어 있으면 채워 넣는다."""
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            userid    TEXT NOT NULL UNIQUE,
            nickname  TEXT NOT NULL,
            password  TEXT NOT NULL,
            created   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS guitars (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            brand     TEXT NOT NULL,
            year      TEXT NOT NULL,
            category  TEXT NOT NULL,
            tagline   TEXT NOT NULL,
            image     TEXT NOT NULL,
            summary   TEXT NOT NULL,
            features  TEXT NOT NULL,   -- 줄바꿈으로 구분한 특징 목록
            specs     TEXT NOT NULL    -- "항목|내용" 을 줄바꿈으로 구분
        );

        CREATE TABLE IF NOT EXISTS posts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL,
            title     TEXT NOT NULL,
            content   TEXT NOT NULL,
            views     INTEGER NOT NULL DEFAULT 0,
            created   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS comments (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id   INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            content   TEXT NOT NULL,
            created   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (post_id) REFERENCES posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    """)

    # 전시 자료는 사용자가 쓰는 데이터가 아니므로 켤 때마다 GUITAR_SEED 내용으로 새로 채운다.
    # (app.py 의 전시 자료를 고치고 다시 실행하면 바로 반영된다. 회원·게시글은 그대로 남는다.)
    db.execute("DELETE FROM guitars")
    db.execute("DELETE FROM sqlite_sequence WHERE name = 'guitars'")
    db.executemany("""
        INSERT INTO guitars (name, brand, year, category, tagline, image, summary, features, specs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, GUITAR_SEED)
    db.commit()
    db.close()


def _g(brand, n):
    return "/static/img/guitars/%s-%d.jpg" % (brand, n)


# 전시할 기타 자료 (사진은 사용자가 준비한 뮤직포스 매장 사진을 잘라 쓴 것)
# 순서: PRS 5대 → Fender 5대 → Gibson 5대. category 칸에는 브랜드를 넣어 전시실처럼 묶는다.
GUITAR_SEED = [
    # ---------------- PRS ----------------
    (
        "커스텀 24 · 파이어 레드 버스트", "PRS", "1985", "PRS",
        "불꽃처럼 번지는 붉은 무늬",
        _g("prs", 1),
        "PRS를 대표하는 커스텀 24 계열의 기타다. 마호가니 몸통 위에 얹은 메이플 상판의 호랑이 무늬가 "
        "가운데의 붉은빛에서 가장자리의 검은빛으로 번지며 불꽃처럼 타오르는 모습을 만든다. "
        "24프렛까지 손이 닿는 넉넉한 지판과 험버커 두 개로 맑은 소리부터 묵직한 소리까지 두루 낸다.",
        "가장자리로 갈수록 어두워지는 파이어 레드 버스트\n결이 또렷한 플레임 메이플 상판\n24프렛 지판과 새 모양 자개 장식\n음을 흔드는 PRS 트레몰로 브리지",
        "바디|마호가니 + 메이플 탑\n넥|마호가니\n픽업|험버커 2개\n스케일|25인치\n프렛 수|24",
    ),
    (
        "커스텀 24 · 차콜 버스트", "PRS", "1985", "PRS",
        "숯처럼 가라앉은 검은 결",
        _g("prs", 2),
        "같은 커스텀 24 계열이지만 색을 검은 숯빛으로 눌러 담아 전혀 다른 인상을 준다. "
        "어두운 바탕 사이로 메이플의 물결무늬가 은빛으로 비쳐 나와, 보는 각도에 따라 결이 살아나고 가라앉는다. "
        "화려한 색 대신 나무결 자체를 보여 주고 싶을 때 고르는 색이다.",
        "검은빛 사이로 은은하게 비치는 플레임 무늬\n크림색 픽업 테두리로 준 대비\n24프렛 지판과 새 모양 자개 장식\n볼륨·톤 두 개로 정리한 단순한 조작부",
        "바디|마호가니 + 메이플 탑\n넥|마호가니\n픽업|험버커 2개\n스케일|25인치\n프렛 수|24",
    ),
    (
        "커스텀 24 · 파이어 레드", "PRS", "1985", "PRS",
        "가운데가 가장 밝게 타오르는 붉은빛",
        _g("prs", 3),
        "1번 전시물과 같은 붉은 계열이지만 가운데의 주황빛이 더 넓게 퍼져 한층 밝고 뜨거운 느낌이다. "
        "같은 모델이라도 나무 한 장마다 무늬가 달라서 두 대를 나란히 놓으면 결의 차이가 뚜렷하게 보인다. "
        "PRS가 상판 나무를 고르는 데 공을 들이는 이유를 보여 주는 한 쌍이다.",
        "넓게 퍼진 주황빛 중심부\n촘촘하고 굵은 플레임 결\n1번 전시물과 견주어 보는 나무 한 장의 차이\n24프렛 지판과 트레몰로 브리지",
        "바디|마호가니 + 메이플 탑\n넥|마호가니\n픽업|험버커 2개\n스케일|25인치\n프렛 수|24",
    ),
    (
        "퀼트 탑 · 차콜 그레이", "PRS", "1985", "PRS",
        "구름이 겹친 듯한 퀼트 무늬",
        _g("prs", 4),
        "메이플 중에서도 물결이 아니라 솜이불을 누빈 듯 둥글게 부풀어 오르는 '퀼트' 무늬를 쓴 기타다. "
        "회색으로 물들여 무늬의 입체감을 더 강하게 살렸고, 몸통 둘레는 칠하지 않은 나무색 테두리를 남겨 "
        "윤곽이 또렷하게 떠오른다. 뿔 안쪽까지 드러난 나무색이 포인트다.",
        "둥글게 부풀어 오르는 퀼트 메이플 상판\n칠하지 않고 남긴 나무색 테두리\n여러 갈래로 소리를 나누는 소형 스위치\n회색 착색으로 강조한 무늬의 입체감",
        "바디|마호가니 + 퀼트 메이플 탑\n넥|마호가니\n픽업|험버커 2개\n스케일|25인치\n마감|차콜 그레이",
    ),
    (
        "퀼트 탑 · 그레이 블랙", "PRS", "1985", "PRS",
        "가장 짙은 그림자를 입은 퀼트",
        _g("prs", 5),
        "4번 전시물과 같은 퀼트 상판을 한층 더 어둡게 물들였다. 색이 짙어질수록 무늬의 볼록한 부분만 빛을 받아 "
        "떠올라서 마치 물속을 들여다보는 듯한 깊이가 생긴다. 조명 아래에서 천천히 돌려 보며 감상하기 좋은 기타다.",
        "검게 가라앉힌 퀼트 무늬\n빛을 받으면 떠오르는 볼록한 결\n나무색 테두리와 뿔 안쪽의 대비\n4번 전시물과 짝을 이루는 색 변주",
        "바디|마호가니 + 퀼트 메이플 탑\n넥|마호가니\n픽업|험버커 2개\n스케일|25인치\n마감|그레이 블랙",
    ),

    # ---------------- Fender ----------------
    (
        "스트라토캐스터 HSS · 화이트", "Fender", "1954", "Fender",
        "흰 몸통에 거북 등껍질 무늬",
        _g("fender", 1),
        "흰 몸통 위에 거북 등껍질 무늬의 픽가드를 얹어 오래된 멋과 깔끔함을 함께 담았다. "
        "앞쪽 두 자리는 맑은 싱글코일, 브리지 쪽은 굵은 험버커를 단 HSS 구성이라 "
        "펜더 특유의 찰랑이는 소리와 록에 어울리는 두꺼운 소리를 한 대로 오갈 수 있다.",
        "싱글코일 2개 + 험버커 1개의 HSS 구성\n토터스 쉘(거북 등껍질) 픽가드\n몸에 맞춰 깎은 콘투어 바디\n음을 흔드는 트레몰로 브리지",
        "바디|앨더\n넥|메이플\n지판|로즈우드\n픽업|싱글코일 2 + 험버커 1\n스케일|25.5인치",
    ),
    (
        "텔레캐스터 · 화이트", "Fender", "1951", "Fender",
        "가장 단순해서 가장 오래 남은 모양",
        _g("fender", 2),
        "펜더가 처음 대량 생산한 일렉트릭 기타의 모양을 그대로 잇는 텔레캐스터다. "
        "판판한 몸통, 픽업 두 개, 줄이 몸통을 뚫고 지나가는 브리지까지 꼭 필요한 것만 남겼다. "
        "흰 몸통과 거북 등껍질 픽가드의 조합은 단정하면서도 존재감이 있다.",
        "군더더기 없이 판판한 싱글컷 몸통\n줄이 몸통을 관통하는 브리지\n쨍하게 튀어나오는 브리지 픽업 소리\n흰 몸통 + 토터스 쉘 픽가드",
        "바디|앨더\n넥|메이플\n지판|로즈우드\n픽업|싱글코일 2개\n스케일|25.5인치",
    ),
    (
        "빈테라 II 60s 텔레캐스터 · 버건디 미스트", "Fender", "1951", "Fender",
        "1960년대를 다시 꺼내 온 금속빛 분홍",
        _g("fender", 3),
        "펜더의 빈테라 II 시리즈는 특정 시대의 기타를 그 시절 방식대로 다시 만드는 라인이다. "
        "이 모델은 1960년대 텔레캐스터를 옮겨 왔고, 그 시절 자동차 도장에서 따온 금속빛 버건디 미스트 색을 입혔다. "
        "민트색 픽가드와 로즈우드 지판이 색을 차분하게 받쳐 준다.",
        "1960년대 사양을 되살린 빈테라 II 시리즈\n자동차 도장에서 온 메탈릭 버건디 미스트\n민트 그린 픽가드\n둥글게 휜 빈티지 지판",
        "바디|앨더\n넥|메이플\n지판|로즈우드\n픽업|빈티지 싱글코일 2개\n시리즈|Vintera II",
    ),
    (
        "플레이어 II 텔레캐스터 · 3톤 선버스트", "Fender", "1951", "Fender",
        "가장 교과서적인 텔레캐스터",
        _g("fender", 4),
        "노랑에서 빨강, 검정으로 번지는 3톤 선버스트에 검은 픽가드, 메이플 지판을 더한 정통 조합이다. "
        "플레이어 II 시리즈는 연주하기 편한 현대식 넥과 지판을 써서 처음 일렉트릭 기타를 잡는 사람에게도 잘 맞는다. "
        "텔레캐스터를 떠올리면 많은 사람이 그리는 바로 그 모습이다.",
        "노랑·빨강·검정으로 번지는 3톤 선버스트\n검은 픽가드와 밝은 메이플 지판\n손에 편한 현대식 넥\n입문자부터 무대까지 쓰는 플레이어 II 라인",
        "바디|앨더\n넥|메이플\n지판|메이플\n픽업|싱글코일 2개\n시리즈|Player II",
    ),
    (
        "플레이어 II 스트라토캐스터 HSS · 레드", "Fender", "1954", "Fender",
        "나무결이 비치는 붉은 스트라토",
        _g("fender", 5),
        "속이 살짝 비치는 붉은 칠 아래로 나무결이 드러나는 스트라토캐스터다. "
        "크림색 픽업과 노브, 흰 픽가드가 붉은 몸통과 선명하게 대비된다. "
        "브리지 쪽 험버커 덕분에 맑은 소리와 힘 있는 소리를 모두 낸다.",
        "나무결이 비치는 반투명 레드 마감\n크림색 픽업·노브와 흰 픽가드\n싱글코일 2 + 험버커 1의 HSS 구성\n메이플 지판의 밝은 인상",
        "바디|앨더\n넥|메이플\n지판|메이플\n픽업|싱글코일 2 + 험버커 1\n시리즈|Player II",
    ),

    # ---------------- Gibson ----------------
    (
        "ES-335 · 빈티지 버스트", "Gibson", "1958", "Gibson",
        "속은 비었지만 가운데는 꽉 찬 몸통",
        _g("gibson", 1),
        "몸통 양옆은 비워 두고 가운데에만 단단한 나무 기둥을 넣은 '세미할로우' 구조의 기타다. "
        "속이 빈 기타의 따뜻한 울림과 꽉 찬 기타의 또렷함을 함께 갖추어 재즈, 블루스, 록을 가리지 않는다. "
        "몸통에 뚫린 f자 모양 구멍이 상징이다.",
        "가운데에 나무 기둥을 넣은 세미할로우 구조\n바이올린을 닮은 f자 울림구멍\n따뜻하면서도 또렷한 소리\n뿔이 둥근 더블 컷어웨이",
        "바디|메이플, 세미할로우\n넥|마호가니\n지판|로즈우드\n픽업|험버커 2개\n스케일|24.75인치",
    ),
    (
        "레스폴 커스텀 · 에보니", "Gibson", "1954", "Gibson",
        "검은 몸통에 금빛 장식, '블랙 뷰티'",
        _g("gibson", 2),
        "레스폴 가운데 가장 격식을 갖춘 모델로, 검은 몸통에 금도금 부품과 여러 겹의 흰 테두리를 둘러 "
        "'블랙 뷰티'라는 별명으로 불린다. 흑단 지판에 네모난 자개를 박아 무대 조명 아래에서 특히 돋보인다.",
        "검은 에보니 마감과 금도금 부품\n몸통을 여러 겹으로 두른 흰 바인딩\n흑단 지판과 네모난 자개 장식\n'블랙 뷰티'라는 별명",
        "바디|마호가니 + 메이플 탑\n넥|마호가니\n지판|흑단\n픽업|험버커 2개\n하드웨어|금도금",
    ),
    (
        "레스폴 스탠다드 P-90 · 토바코 버스트", "Gibson", "1952", "Gibson",
        "험버커 이전의 레스폴 소리",
        _g("gibson", 3),
        "레스폴이 처음 나왔을 때 달려 있던 P-90 픽업을 그대로 쓴 모델이다. "
        "크림색 비누 모양 픽업 두 개가 험버커보다 거칠고 생기 있는 소리를 낸다. "
        "담뱃잎처럼 짙은 갈색에서 호박빛으로 번지는 토바코 버스트가 오래된 멋을 더한다.",
        "크림색 P-90 픽업 2개\n험버커보다 거칠고 생기 있는 소리\n짙은 갈색에서 호박빛으로 번지는 토바코 버스트\n크림색 픽가드와 금빛 노브",
        "바디|마호가니 + 메이플 탑\n넥|마호가니\n지판|로즈우드\n픽업|P-90 2개\n스케일|24.75인치",
    ),
    (
        "레스폴 스탠다드 · 버스트", "Gibson", "1952", "Gibson",
        "가장 많은 무대에 오른 레스폴",
        _g("gibson", 4),
        "험버커 두 개를 단, 가장 익숙한 모습의 레스폴 스탠다드다. "
        "마호가니 몸통과 메이플 상판이 만드는 두껍고 길게 이어지는 소리는 하드록의 기준이 되었다. "
        "3번 전시물과 나란히 보면 픽업 하나로 생김새와 소리가 얼마나 달라지는지 알 수 있다.",
        "두툼한 험버커 픽업 2개\n길게 이어지는 서스테인\n짙은 테두리에서 밝은 가운데로 번지는 버스트\n3번(P-90)과 견주어 보는 픽업의 차이",
        "바디|마호가니 + 메이플 탑\n넥|마호가니\n지판|로즈우드\n픽업|험버커 2개\n스케일|24.75인치",
    ),
    (
        "레스폴 스페셜 · TV 옐로우", "Gibson", "1955", "Gibson",
        "흑백 TV에서 잘 보이라고 칠한 노랑",
        _g("gibson", 5),
        "상판 없이 마호가니 한 덩어리로 만든 몸통에 P-90 두 개와 단순한 브리지를 단 실속형 레스폴이다. "
        "'TV 옐로우'라는 색 이름은 흑백 텔레비전 시절 화면에서 흰색보다 덜 번쩍이고 잘 보이도록 고른 색이라는 데서 왔다. "
        "가볍고 거친 소리로 펑크와 록 밴드들이 즐겨 썼다.",
        "상판 없이 마호가니 한 덩어리로 만든 몸통\nP-90 픽업 2개의 거친 소리\n줄을 감아 거는 단순한 랩어라운드 브리지\n흑백 TV 시절에서 온 'TV 옐로우'",
        "바디|마호가니\n넥|마호가니\n지판|로즈우드\n픽업|P-90 2개\n브리지|랩어라운드",
    ),
]


# ------------------------------------------------------------------
# 로그인 도우미
# ------------------------------------------------------------------
def login_required(view):
    """로그인하지 않은 사람이 들어오면 로그인 화면으로 보낸다."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("로그인이 필요한 기능입니다.")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_user():
    """모든 화면에서 로그인한 사람의 별명을 쓸 수 있게 한다."""
    return {"login_user": session.get("nickname")}


# ------------------------------------------------------------------
# 전시관
# ------------------------------------------------------------------
@app.route("/")
def index():
    db = get_db()
    category = request.args.get("category", "전체")
    guitars = db.execute("SELECT * FROM guitars ORDER BY id").fetchall()

    # 브랜드별 전시실로 묶는다 (전시 자료에 넣은 순서 그대로)
    brands = []
    for g_row in guitars:
        if g_row["category"] not in brands:
            brands.append(g_row["category"])

    rooms = []
    for b in brands:
        if category in ("전체", b):
            rooms.append({
                "brand": b,
                "intro": BRAND_INTRO.get(b, ""),
                "items": [g_row for g_row in guitars if g_row["category"] == b],
            })

    # 첫 화면에 걸어 둘 대표작: 전시실마다 첫 번째 기타
    featured = [next(g_row for g_row in guitars if g_row["category"] == b) for b in brands]

    return render_template("index.html", rooms=rooms, total=len(guitars),
                           categories=["전체"] + brands, current=category,
                           featured=featured, guitars=guitars)


BRAND_INTRO = {
    "PRS": "나무 한 장의 무늬를 작품처럼 다루는 미국 메릴랜드의 공방. 상판의 결을 보는 전시실입니다.",
    "Fender": "일렉트릭 기타와 베이스의 모양을 처음 정한 회사. 단순한 몸통에서 나오는 맑은 소리를 봅니다.",
    "Gibson": "마호가니와 메이플, 험버커로 두꺼운 소리를 만든 회사. 레스폴과 ES 계열을 모았습니다.",
}


@app.route("/guitar/<int:guitar_id>")
def guitar(guitar_id):
    db = get_db()
    item = db.execute("SELECT * FROM guitars WHERE id = ?", (guitar_id,)).fetchone()
    if item is None:
        flash("없는 전시물입니다.")
        return redirect(url_for("index"))

    prev_item = db.execute("SELECT id, name FROM guitars WHERE id < ? ORDER BY id DESC LIMIT 1",
                           (guitar_id,)).fetchone()
    next_item = db.execute("SELECT id, name FROM guitars WHERE id > ? ORDER BY id LIMIT 1",
                           (guitar_id,)).fetchone()

    features = [f for f in item["features"].split("\n") if f.strip()]
    specs = [line.split("|") for line in item["specs"].split("\n") if "|" in line]
    return render_template("detail.html", item=item, features=features, specs=specs,
                           prev_item=prev_item, next_item=next_item)


@app.route("/map")
def store_map():
    return render_template("map.html")


# ------------------------------------------------------------------
# 회원가입 / 로그인
# ------------------------------------------------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        userid = request.form.get("userid", "").strip()
        nickname = request.form.get("nickname", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        error = None
        if len(userid) < 4:
            error = "아이디는 4자 이상 입력하세요."
        elif not nickname:
            error = "별명을 입력하세요."
        elif len(password) < 4:
            error = "비밀번호는 4자 이상 입력하세요."
        elif password != password2:
            error = "비밀번호가 서로 다릅니다."
        else:
            db = get_db()
            exists = db.execute("SELECT 1 FROM users WHERE userid = ?", (userid,)).fetchone()
            if exists:
                error = "이미 쓰고 있는 아이디입니다."

        if error:
            flash(error)
            return render_template("signup.html", userid=userid, nickname=nickname)

        db = get_db()
        # 비밀번호는 그대로 저장하지 않고 암호화해서 넣는다
        db.execute("INSERT INTO users (userid, nickname, password) VALUES (?, ?, ?)",
                   (userid, nickname, generate_password_hash(password)))
        db.commit()
        flash("회원가입이 끝났습니다. 로그인해 주세요.")
        return redirect(url_for("login"))

    return render_template("signup.html", userid="", nickname="")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        userid = request.form.get("userid", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE userid = ?", (userid,)).fetchone()
        if user is None or not check_password_hash(user["password"], password):
            flash("아이디나 비밀번호가 맞지 않습니다.")
            return render_template("login.html", userid=userid)

        session.clear()
        session["user_id"] = user["id"]
        session["nickname"] = user["nickname"]
        flash(user["nickname"] + "님 반갑습니다.")

        target = request.args.get("next")
        return redirect(target if target else url_for("index"))

    return render_template("login.html", userid="")


@app.route("/logout")
def logout():
    session.clear()
    flash("로그아웃했습니다.")
    return redirect(url_for("index"))


# ------------------------------------------------------------------
# 게시판
# ------------------------------------------------------------------
PAGE_SIZE = 10


@app.route("/board")
def board():
    db = get_db()
    keyword = request.args.get("q", "").strip()
    page = max(1, request.args.get("page", 1, type=int))

    where, params = "", []
    if keyword:
        where = "WHERE p.title LIKE ? OR p.content LIKE ?"
        params = ["%" + keyword + "%", "%" + keyword + "%"]

    total = db.execute("SELECT COUNT(*) FROM posts p " + where, params).fetchone()[0]
    posts = db.execute("""
        SELECT p.*, u.nickname,
               (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count
        FROM posts p JOIN users u ON p.user_id = u.id
        """ + where + " ORDER BY p.id DESC LIMIT ? OFFSET ?",
        params + [PAGE_SIZE, (page - 1) * PAGE_SIZE]).fetchall()

    last_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    return render_template("board.html", posts=posts, page=page,
                           last_page=last_page, keyword=keyword, total=total)


@app.route("/board/write", methods=["GET", "POST"])
@login_required
def write():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("제목과 내용을 모두 입력하세요.")
            return render_template("post_form.html", post=None, title=title, content=content)

        db = get_db()
        cur = db.execute("INSERT INTO posts (user_id, title, content) VALUES (?, ?, ?)",
                         (session["user_id"], title, content))
        db.commit()
        return redirect(url_for("post_view", post_id=cur.lastrowid))

    return render_template("post_form.html", post=None, title="", content="")


@app.route("/board/<int:post_id>")
def post_view(post_id):
    db = get_db()
    db.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))
    db.commit()

    post = db.execute("""
        SELECT p.*, u.nickname FROM posts p JOIN users u ON p.user_id = u.id
        WHERE p.id = ?""", (post_id,)).fetchone()
    if post is None:
        flash("없는 글입니다.")
        return redirect(url_for("board"))

    comments = db.execute("""
        SELECT c.*, u.nickname FROM comments c JOIN users u ON c.user_id = u.id
        WHERE c.post_id = ? ORDER BY c.id""", (post_id,)).fetchall()
    return render_template("post_view.html", post=post, comments=comments)


@app.route("/board/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def post_edit(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        flash("없는 글입니다.")
        return redirect(url_for("board"))
    if post["user_id"] != session["user_id"]:       # 쓴 사람만 고칠 수 있다
        flash("내가 쓴 글만 고칠 수 있습니다.")
        return redirect(url_for("post_view", post_id=post_id))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("제목과 내용을 모두 입력하세요.")
            return render_template("post_form.html", post=post, title=title, content=content)

        db.execute("UPDATE posts SET title = ?, content = ? WHERE id = ?",
                   (title, content, post_id))
        db.commit()
        return redirect(url_for("post_view", post_id=post_id))

    return render_template("post_form.html", post=post,
                           title=post["title"], content=post["content"])


@app.route("/board/<int:post_id>/delete", methods=["POST"])
@login_required
def post_delete(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        flash("없는 글입니다.")
    elif post["user_id"] != session["user_id"]:
        flash("내가 쓴 글만 지울 수 있습니다.")
        return redirect(url_for("post_view", post_id=post_id))
    else:
        db.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
        db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        db.commit()
        flash("글을 지웠습니다.")
    return redirect(url_for("board"))


@app.route("/board/<int:post_id>/comment", methods=["POST"])
@login_required
def comment_write(post_id):
    content = request.form.get("content", "").strip()
    if content:
        db = get_db()
        db.execute("INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)",
                   (post_id, session["user_id"], content))
        db.commit()
    else:
        flash("댓글 내용을 입력하세요.")
    return redirect(url_for("post_view", post_id=post_id))


@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def comment_delete(comment_id):
    db = get_db()
    comment = db.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if comment is None:
        return redirect(url_for("board"))
    if comment["user_id"] != session["user_id"]:
        flash("내가 쓴 댓글만 지울 수 있습니다.")
    else:
        db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        db.commit()
    return redirect(url_for("post_view", post_id=comment["post_id"]))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
