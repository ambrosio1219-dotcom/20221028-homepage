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
import re
import sqlite3
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Vercel 서버는 /tmp 에만 파일을 쓸 수 있다. 그곳의 DB는 서버가 다시 켜지면 비워진다.
if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/gallery.db"
else:
    DB_PATH = os.path.join(BASE_DIR, "gallery.db")

# Vercel 에 연결한 Neon(Postgres) 주소. 이 값이 있으면 SQLite 대신 Postgres 를 쓴다.
# Vercel 은 서버를 여러 대 띄우는데 /tmp 의 SQLite 는 서버마다 따로라서,
# 글을 쓴 서버와 목록을 보여 주는 서버가 다르면 글이 사라진 것처럼 보였다.
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

# 화면 파일(html)은 templates 폴더가 아니라 맨 위에 둔다.
# static 폴더는 쓰지 않고, 아래 assets() 로 css·js·img 세 폴더만 주소로 열어 준다.
app = Flask(__name__, template_folder=".", static_folder=None)
# 세션(로그인 상태)을 암호화하는 열쇠. 실제 서비스라면 외부에 노출하면 안 된다.
app.secret_key = "midterm-guitar-gallery-secret-key"


# 맨 위 폴더를 통째로 열면 app.py 나 gallery.db 까지 내려받을 수 있으므로 세 폴더만 연다
@app.route("/<any(css, js, img):folder>/<path:filename>")
def assets(folder, filename):
    return send_from_directory(os.path.join(BASE_DIR, folder), filename)


# ------------------------------------------------------------------
# 데이터베이스
# ------------------------------------------------------------------
class PgRow(dict):
    """sqlite3.Row 처럼 row["이름"] 과 row[0] 둘 다 되게 한다."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return dict.__getitem__(self, key)


def _pg_row_factory(cursor):
    names = [c.name for c in cursor.description or []]
    return lambda values: PgRow(zip(names, values))


class PgResult:
    """db.execute() 의 결과. SQLite 커서처럼 fetchone, fetchall, lastrowid 를 쓴다."""
    def __init__(self, cursor, lastrowid=None):
        self.cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class PgDB:
    """Postgres 연결을 sqlite3 연결처럼 쓸 수 있게 감싼다.
    덕분에 아래 화면 코드의 SQL("... WHERE id = ?")은 SQLite 와 똑같이 쓴다."""
    # 한국 시간(UTC+9). 시간대 이름 대신 +09:00 으로 적어 시간대 자료가 없는 서버에서도 동작한다.
    SEOUL_NOW = "(to_char(now() AT TIME ZONE INTERVAL '+09:00', 'YYYY-MM-DD HH24:MI:SS'))"

    def __init__(self, url):
        import psycopg      # 내 컴퓨터(SQLite)에서는 설치하지 않아도 되게 여기서 불러온다
        # prepare_threshold=None: Neon 의 연결 공유(PgBouncer)와 충돌하지 않게 미리 준비된 문장을 쓰지 않는다
        self.conn = psycopg.connect(url, row_factory=_pg_row_factory, prepare_threshold=None)

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")
        if sql.lstrip().upper().startswith("INSERT"):
            # SQLite 의 cur.lastrowid 대신 새 번호를 돌려받는다
            cur = self.conn.execute(sql + " RETURNING id", params)
            return PgResult(cur, cur.fetchone()["id"])
        return PgResult(self.conn.execute(sql, params))

    def executemany(self, sql, seq):
        with self.conn.cursor() as cur:
            cur.executemany(sql.replace("?", "%s"), seq)

    def executescript(self, script):
        # 표 만드는 SQL 을 Postgres 문법으로 바꿔서 한 문장씩 실행한다
        script = (script.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
                        .replace("(datetime('now', 'localtime'))", self.SEOUL_NOW))
        for stmt in script.split(";"):
            if stmt.strip():
                self.conn.execute(stmt)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def connect():
    """Postgres 주소가 있으면 Postgres, 없으면 SQLite 파일에 연결한다."""
    if DATABASE_URL:
        return PgDB(DATABASE_URL)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row      # 컬럼 이름으로 꺼내 쓰기 위해
    return db


def get_db():
    """요청 한 번에 연결 하나만 쓰도록 g 객체에 담아 둔다."""
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """표가 없으면 만들고, 전시할 기타 자료가 비어 있으면 채워 넣는다."""
    db = connect()
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
    if DATABASE_URL:
        db.execute("TRUNCATE guitars RESTART IDENTITY")     # 비우고 번호도 1부터
    else:
        db.execute("DELETE FROM guitars")
        db.execute("DELETE FROM sqlite_sequence WHERE name = 'guitars'")
    db.executemany("""
        INSERT INTO guitars (name, brand, year, category, tagline, image, summary, features, specs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, GUITAR_SEED)
    db.commit()
    db.close()


def _g(brand, n):
    return "/img/guitars/%s-%d.jpg" % (brand, n)


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


@app.before_request
def check_login_user():
    """쿠키 속 회원 번호가 DB의 같은 회원을 가리키는지 확인하고, 아니면 로그아웃시킨다.
    (DB를 바꾸면 예전 쿠키의 번호가 다른 사람을 가리켜, 남의 이름으로 글이 써질 수 있다)"""
    if "user_id" not in session or request.endpoint == "assets":
        return
    user = get_db().execute("SELECT userid FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if user is None or user["userid"] != session.get("userid"):
        session.clear()
        flash("로그인 정보가 바뀌어 로그아웃되었습니다. 다시 로그인해 주세요.")


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

    return render_template("index.html", rooms=rooms, total=len(guitars),
                           categories=["전체"] + brands, current=category,
                           guitars=guitars)


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
# 기타 안내 (처음 보는 사람을 위한 생김새 · 용어 · 역사)
# ------------------------------------------------------------------
# 안내 페이지 기타 그림의 번호와 같은 순서
GUIDE_PARTS = [
    ("헤드", "Headstock", "넥 끝의 넓적한 부분. 줄감개가 달리고, 회사마다 모양이 달라 기타의 얼굴 역할을 한다."),
    ("줄감개", "Tuning Pegs", "줄을 감거나 풀어서 음 높이를 맞추는 손잡이. 줄 하나에 하나씩, 모두 여섯 개다."),
    ("너트", "Nut", "헤드와 지판 사이의 작은 막대. 줄 간격을 잡아 주고, 줄이 떨리기 시작하는 지점이다."),
    ("지판 · 프렛", "Fretboard · Frets", "왼손으로 줄을 누르는 면과 그 위에 박힌 금속 막대. 프렛 한 칸을 옮길 때마다 음이 반음씩 바뀐다."),
    ("넥", "Neck", "몸통에서 길게 뻗은 손잡이. 두께와 모양에 따라 손에 잡히는 느낌이 달라진다."),
    ("줄", "Strings", "여섯 가닥의 쇠줄. 굵은 줄일수록 낮은 소리가 난다."),
    ("픽업 셀렉터", "Selector Switch", "여러 픽업 가운데 어느 것의 소리를 낼지 고르는 스위치."),
    ("픽업", "Pickups", "줄의 떨림을 전기 신호로 바꾸는 장치. 일렉 기타 소리의 성격을 가장 크게 좌우한다."),
    ("바디", "Body", "기타의 몸통. 나무 종류와 모양, 속이 찼는지 비었는지가 소리와 무게를 정한다."),
    ("브리지", "Bridge", "몸통에서 줄을 붙잡아 두는 부품. 줄 높이와 음정을 미세하게 맞출 수 있다."),
    ("노브", "Knobs", "소리 크기(볼륨)와 음색(톤)을 조절하는 돌림 손잡이."),
]

# 전시물 설명에 나오는 용어. 안내 페이지에는 묶음별로 보여 주고, 상세 페이지에서는 말풍선으로 띄운다.
GLOSSARY_GROUPS = [
    ("픽업 종류", [
        ("싱글코일", "코일이 하나인 픽업. 맑고 찰랑이는 소리가 나지만 잡음이 조금 섞이기 쉽다. 펜더 기타의 상징이다."),
        ("험버커", "코일 두 개를 붙여 '웅' 하는 잡음(험)을 없앤 픽업. 두껍고 힘 있는 소리를 낸다. 깁슨과 PRS가 주로 쓴다."),
        ("P-90", "깁슨의 초창기 싱글코일 픽업. 보통 싱글코일보다 굵고 거친 소리를 낸다. 크림색 비누처럼 생겼다."),
        ("HSS", "픽업 배치를 줄인 말. 브리지 쪽에 험버커(H) 하나, 나머지 두 자리에 싱글코일(S) 두 개를 단 구성이다."),
    ]),
    ("나무", [
        ("마호가니", "붉은 갈색의 묵직한 나무. 중저음이 두툼하고 따뜻한 소리를 낸다. 깁슨과 PRS의 몸통·넥에 많이 쓴다."),
        ("메이플", "밝은 색의 단단한 나무. 소리가 또렷하고 밝다. 상판, 넥, 지판에 두루 쓴다."),
        ("앨더", "가볍고 소리가 고르게 퍼지는 나무. 펜더 몸통의 대표 재료다."),
        ("로즈우드", "짙은 갈색의 기름기 있는 나무. 지판에 많이 쓰며 손끝에 닿는 느낌이 부드럽다."),
        ("흑단", "검고 아주 단단한 나무(에보니). 고급 기타의 지판에 쓰며 소리가 또렷하다."),
        ("상판", "몸통 윗면에 덧붙인 나무판('탑'). 무늬가 고운 메이플을 얹어 보기 좋게 하고 소리를 밝게 한다."),
        ("플레임", "메이플에 나타나는 호랑이 줄무늬 같은 결. 보는 각도에 따라 일렁이듯 반짝인다."),
        ("퀼트", "메이플에 나타나는, 솜이불을 누빈 듯 둥글게 부푼 무늬. 플레임보다 드물다."),
    ]),
    ("몸통 모양", [
        ("싱글컷", "넥 옆을 한쪽만 파낸 몸통 모양. 레스폴과 텔레캐스터가 대표적이다."),
        ("더블 컷어웨이", "넥 양옆을 모두 파낸 몸통 모양. 높은 프렛까지 손이 잘 닿는다."),
        ("콘투어 바디", "몸에 닿는 부분을 둥글게 깎아 낸 몸통. 오래 메고 연주해도 편하다."),
        ("세미할로우", "몸통 양옆은 비우고 가운데에만 나무 기둥을 넣은 구조. 속 빈 기타의 울림과 꽉 찬 기타의 또렷함을 함께 갖는다."),
        ("f자 울림구멍", "바이올린처럼 몸통에 뚫은 f 모양 구멍. 속이 빈 기타의 울림을 밖으로 내보낸다."),
        ("스케일", "너트에서 브리지까지 줄이 떨리는 길이. 길면(펜더 25.5인치) 팽팽하고 쨍한 소리, 짧으면(깁슨 24.75인치) 부드러운 소리가 난다."),
    ]),
    ("부품 · 장식", [
        ("트레몰로", "손잡이(암)로 브리지를 움직여 음을 출렁이게 하는 장치."),
        ("랩어라운드", "줄을 브리지 뒤쪽에서 감아 걸어 앞으로 넘기는 단순한 브리지."),
        ("픽가드", "피크에 몸통이 긁히지 않도록 붙인 얇은 판. 색과 무늬에 따라 기타의 인상이 크게 달라진다."),
        ("바인딩", "몸통이나 지판 가장자리에 두른 띠. 나무를 보호하고 윤곽을 또렷하게 보여 준다."),
        ("자개", "조개껍데기 안쪽의 반짝이는 부분. 지판에 박아 위치 표시와 장식으로 쓴다."),
        ("금도금", "금속 부품에 금을 얇게 입힌 것. 고급 모델에 화려함을 더한다."),
        ("하드웨어", "브리지, 줄감개, 노브처럼 기타에 달린 금속 부품을 통틀어 이르는 말."),
    ]),
    ("색과 소리", [
        ("선버스트", "가운데는 밝고 가장자리로 갈수록 어두워지는 칠. 해가 퍼지는 모양에서 온 이름이다."),
        ("마감", "기타 겉면의 칠. 색뿐 아니라 광택과 나무결이 비치는 정도까지 정한다."),
        ("토터스 쉘", "거북 등껍질 무늬. 픽가드에 많이 쓰는 오래된 멋의 무늬다."),
        ("서스테인", "줄을 한 번 튕긴 뒤 소리가 이어지는 길이. 길수록 음이 오래 울린다."),
    ]),
]

# 기본 부위는 안내 페이지 그림에서 설명하므로 용어 묶음에는 넣지 않고 말풍선에만 쓴다
PART_TERMS = {
    "바디": "기타의 몸통. 나무 종류와 모양이 소리와 무게를 정한다.",
    "넥": "몸통에서 길게 뻗은 손잡이 부분. 왼손으로 잡고 줄을 누른다.",
    "지판": "넥 앞면에 붙인 판. 손가락으로 줄을 누르는 면이다.",
    "프렛": "지판에 박힌 금속 막대. 한 칸 옮길 때마다 음이 반음씩 바뀐다.",
    "픽업": "줄의 떨림을 전기 신호로 바꾸는 장치. 소리의 성격을 가장 크게 좌우한다.",
    "브리지": "몸통에서 줄을 붙잡아 두는 부품.",
    "노브": "소리 크기(볼륨)와 음색(톤)을 조절하는 돌림 손잡이.",
}

GLOSSARY = dict(PART_TERMS)
for _group, _terms in GLOSSARY_GROUPS:
    GLOSSARY.update(_terms)

# 글에서 다른 모양으로 나오는 말 → 사전의 용어
TERM_ALIASES = {"탑": "상판", "버스트": "선버스트", "f자": "f자 울림구멍"}

# 긴 말부터 찾아야 "콘투어 바디"가 "바디"보다 먼저 잡힌다. 앞에 다른 글자가 붙은 말(예: 커넥)은 건너뛴다.
_TERM_RE = re.compile(r"(?<![가-힣A-Za-z])(" + "|".join(
    re.escape(t) for t in sorted(list(GLOSSARY) + list(TERM_ALIASES), key=len, reverse=True)) + ")")


@app.template_filter("tips")
def tips(text):
    """글 속 기타 용어에 누르면 설명이 뜨는 말풍선을 붙인다. 한 화면에서 같은 용어는 처음 한 번만."""
    seen = g.setdefault("tip_seen", set())

    def wrap(m):
        word = m.group(1)
        term = TERM_ALIASES.get(word, word)
        if term in seen:
            return word
        seen.add(term)
        desc = escape(GLOSSARY[term])
        return '<span class="term" tabindex="0" data-tip="%s" aria-label="%s: %s">%s</span>' % (
            desc, escape(word), desc, word)

    return Markup(_TERM_RE.sub(wrap, str(escape(text))))


BRAND_HISTORY = [
    ("1902", "Gibson", "깁슨 회사 설립",
     "미국 미시간주 칼라마주에서, 만돌린과 기타를 만들던 오빌 깁슨의 이름을 딴 회사가 세워졌다."),
    ("1946", "Fender", "펜더 회사 설립",
     "라디오 수리점을 하던 레오 펜더가 캘리포니아 풀러턴에서 회사를 세웠다."),
    ("1951", "Fender", "텔레캐스터",
     "1950년 '브로드캐스터'라는 이름으로 나왔다가 지금 이름이 되었다. 대량 생산된 첫 솔리드 바디 일렉트릭 기타로 꼽힌다."),
    ("1952", "Gibson", "레스폴",
     "기타리스트 레스 폴과 함께 만든 깁슨의 첫 솔리드 바디 기타. 처음에는 P-90 픽업을 달았다."),
    ("1954", "Fender", "스트라토캐스터",
     "몸에 맞춰 깎은 몸통, 싱글코일 세 개, 트레몰로 브리지로 지금까지 가장 널리 쓰이는 모양이 되었다."),
    ("1954", "Gibson", "레스폴 커스텀",
     "검은 몸통에 금빛 부품을 단 고급형. '블랙 뷰티'라는 별명이 붙었다."),
    ("1957", "Gibson", "험버커 픽업",
     "잡음을 없앤 험버커 픽업이 깁슨 기타에 달리기 시작해, 레스폴 소리의 기준이 되었다."),
    ("1958", "Gibson", "ES-335",
     "속을 반쯤 비운 세미할로우 구조로 재즈부터 록까지 두루 쓰이게 되었다."),
    ("1985", "PRS", "PRS 설립",
     "폴 리드 스미스가 메릴랜드주 아나폴리스에서 회사를 세우고, 첫 모델인 커스텀(지금의 커스텀 24)을 내놓았다."),
]


@app.route("/guide")
def guide():
    return render_template("guide.html", parts=GUIDE_PARTS, groups=GLOSSARY_GROUPS,
                           history=BRAND_HISTORY)


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
        session["userid"] = user["userid"]       # check_login_user() 가 회원 번호와 함께 확인한다
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


# 서버가 켜질 때 표를 준비한다 (Vercel 은 python app.py 로 켜지 않으므로 여기서 부른다)
init_db()

if __name__ == "__main__":
    app.run(debug=True)
