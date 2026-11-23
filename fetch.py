"""維持できなくなる町：国立社会保障・人口問題研究所「日本の地域別将来推計人口（令和5(2023)年推計）」から、
2020年→2050年の人口の減り方・高齢化・子どもの減り方を市区町村ごとに並べる。"""
import io
import re

from lib import oc

PAGE = "https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/t-page.asp"
TOP = "https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/"


class Sheet:
    def __init__(self, title, rows):
        self.title, self.rows = title, rows


def sheets():
    import pandas as pd
    urls = oc.links(PAGE, r"\.xlsx?$")
    oc.check(urls, "推計結果の表が見つかりません")
    for u in urls:
        b = oc.get(u, cache="ipss_" + u.rsplit("/", 1)[-1])
        try:
            book = pd.read_excel(io.BytesIO(b), sheet_name=None, header=None)
        except Exception as e:
            oc.log("skip", u, e)
            continue
        for name, df in book.items():
            yield u, Sheet(str(name), [tuple(None if (isinstance(v, float) and v != v) else v for v in r) for r in df.itertuples(index=False)])


def parse(ws):
    """「コード」「市区町村」と、年（2020…2050）が並ぶ見出し行を探し、総人口・0〜14歳・65歳以上を取る。"""
    rows = ws.rows
    for hi, h in enumerate(rows[:15]):
        cells = [str(c or "") for c in h]
        years = {i: int(re.search(r"(20\d\d)", c).group(1)) for i, c in enumerate(cells) if re.search(r"20[2-5]\d", c)}
        if 2020 in years.values() and 2050 in years.values() and any("コード" in c for c in cells):
            ci = next(i for i, c in enumerate(cells) if "コード" in c)
            ni = next((i for i, c in enumerate(cells) if "市区町村" in c or "地域" in c or "名" in c), ci + 1)
            yi = {y: i for i, y in years.items()}
            out = []
            for r in rows[hi + 1:]:
                code = re.sub(r"\D", "", str(r[ci] or ""))
                if len(code) < 4:
                    continue
                out.append((code.zfill(5)[:5], str(r[ni] or "").strip(), oc.num(r[yi[2020]]), oc.num(r[yi[2050]])))
            return out
    return None


def run():
    data = {}  # 指標 -> {code: (name, 2020, 2050)}
    for u, ws in sheets():
        t = ws.title + " " + u
        kind = "total" if re.search(r"総数|総人口|男女計", t) else "kids" if re.search(r"0.?～?14|年少", t) else \
            "old" if re.search(r"65|老年", t) else None
        res = parse(ws)
        if not res:
            continue
        kind = kind or "total"
        d = data.setdefault(kind, {})
        for code, name, a, b in res:
            if a and b is not None and not code.endswith("000"):
                d[code] = (name, a, b)
        oc.log(u.rsplit("/", 1)[-1], ws.title, kind, len(res))
    tot = data.get("total", {})
    oc.check(len(tot) > 1500, "市区町村の数が少なすぎます(%d)" % len(tot))
    s20 = sum(v[1] for v in tot.values()); s50 = sum(v[2] for v in tot.values())
    oc.check(1.0e8 < s20 < 1.4e8 and 0.8e8 < s50 < s20, "全国の合計が想定外です(%d→%d)" % (s20, s50))
    rows = []
    for code, (name, a, b) in tot.items():
        k = data.get("kids", {}).get(code); o = data.get("old", {}).get(code)
        rows.append({"city": name, "pref": oc.pref_name(code), "p20": a, "p50": b, "chg": b / a - 1,
                     "kid": (k[2] / k[1] - 1) if k and k[1] else None, "old50": (o[2] / b) if o and b else None})
    cols = [{"key": "city", "label": "市区町村"}, {"key": "pref", "label": "都道府県"},
            {"key": "chg", "label": "2050年までの人口増減", "type": "num", "fmt": "pct", "bar": True},
            {"key": "kid", "label": "子ども（0〜14歳）の増減", "type": "num", "fmt": "pct"},
            {"key": "old50", "label": "2050年の65歳以上の割合", "type": "num", "fmt": "pct"},
            {"key": "p20", "label": "2020年人口", "type": "num"}, {"key": "p50", "label": "2050年人口（推計）", "type": "num"}]
    for r in rows:
        r["loss"] = -r["chg"]
    cols_loss = [dict(c, key="loss", label="2050年までに減る割合") if c["key"] == "chg" else c for c in cols]
    worst = sorted(rows, key=lambda r: r["chg"])
    best = sorted(rows, key=lambda r: -r["chg"])
    old = sorted([r for r in rows if r["old50"] is not None], key=lambda r: -r["old50"])
    half = [r for r in rows if r["chg"] <= -0.5]
    meth = ("社人研の公式推計（2023年推計）の市区町村別人口を使い、2020年（国勢調査）と2050年（推計）を比べました。"
            "推計は「今の傾向が続いたら」の見通しで、政策や移住で変わります。福島県の一部町村など推計がない地域は含みません。")
    R = [{"id": "loss", "tab": "減り方", "title": "2050年までに人口が大きく減る市区町村",
          "desc": "2020年から2050年までに人口が何割減るか（推計）。", "rows": worst, "columns": cols_loss, "method": meth,
          "trend": oc.trend(worst, "pref", 100, "市区町村", "市区町村"), "share_label": "city", "share_value": "loss"},
         {"id": "old", "tab": "高齢化", "title": "2050年に高齢者の割合が高い市区町村",
          "desc": "2050年に住民の何割が65歳以上になるか（推計）。", "rows": old, "columns": cols, "method": meth,
          "trend": oc.trend(old, "pref", 100, "市区町村", "市区町村"), "share_label": "city", "share_value": "old50"},
         {"id": "grow", "tab": "増える町", "title": "2050年も人口が減らない・減り方が小さい市区町村",
          "rows": best, "columns": cols, "method": meth, "trend": oc.trend(best, "pref", 50, "市区町村", "市区町村"),
          "share_label": "city", "share_value": "chg"}]
    meta = {"data_period": "2020年（国勢調査）→2050年（推計）",
            "stats": [{"label": "人口が半分以下になる市区町村", "value": len(half), "unit": "市区町村"},
                      {"label": "全国の人口の増減（2020→2050）", "value": s50 / s20 - 1, "fmt": "pct"},
                      {"label": "推計がある市区町村", "value": len(rows), "unit": "市区町村"}],
            "sources": [{"name": "日本の地域別将来推計人口（令和5(2023)年推計）", "org": "国立社会保障・人口問題研究所", "url": PAGE,
                         "license": "出典を明記して利用"}]}
    oc.write(meta, R, search=[{"n": r["city"], "s": r["pref"], "k": [["2050年までの増減", "%.1f%%" % (r["chg"] * 100)]]} for r in rows])


if __name__ == "__main__":
    oc.main(run)
