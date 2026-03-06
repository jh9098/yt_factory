from __future__ import annotations

import datetime as dt
import os
import re

import yt_dlp

API_KEY = "미공개"
FALLBACK_CHANNELS = []

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:
    build = None
    HttpError = Exception


class QuietLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)


def _build_ydl_opts(base_opts: dict = None) -> dict:
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "forcejson": True,
        "simulate": True,
        "http_headers": {"User-Agent": "Mozilla/5.0"},
        "extractor_args": {"youtube": {"player_client": ["android", "ios"], "skip": ["dash", "hls"]}},
    }
    if base_opts:
        ydl_opts.update(base_opts)
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
    if proxy_url:
        ydl_opts["proxy"] = proxy_url
    return ydl_opts


_CUE_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}")
_CHANNEL_ID_RE = re.compile(r"^UC[0-9A-Za-z_-]{22,}$")
_ISO8601_DUR = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def clean_vtt(vtt_text: str) -> str:
    lines = vtt_text.splitlines()
    result = []
    prev = ""
    for line in lines:
        if _CUE_RE.match(line):
            continue
        if line.strip().startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "align:", "position:")):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean != prev:
            result.append(clean)
            prev = clean
    return "\n".join(result)


def extract_text_and_title(youtube_url: str, cookie_path: str = ""):
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "quiet": True,
        "forcejson": True,
        "simulate": True,
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }
    if cookie_path and os.path.exists(cookie_path):
        opts["cookiefile"] = cookie_path
    ydl_opts = _build_ydl_opts(opts)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        title = info.get("title") or "video"
        subs = info.get("subtitles") or {}
        auto_subs = info.get("automatic_captions") or {}

        def get_vtt(sub_dict, preferred=("ko", "ko-KR", "ko_KR", "en")):
            for lang in preferred:
                if lang in sub_dict:
                    for f in sub_dict[lang]:
                        if f.get("ext") == "vtt":
                            return ydl.urlopen(f["url"]).read().decode("utf-8")
            for _, formats in sub_dict.items():
                for f in formats:
                    if f.get("ext") == "vtt":
                        return ydl.urlopen(f["url"]).read().decode("utf-8")
            return None

        vtt_text = get_vtt(subs) or get_vtt(auto_subs)
        if not vtt_text:
            return None, title
        return clean_vtt(vtt_text), title


def _resolve_api_key() -> str:
    if API_KEY and API_KEY.strip():
        return API_KEY.strip()
    return (os.environ.get("YOUTUBE_API_KEY", "")).strip()


def _format_upload_datestr_iso8601_to_pair(iso_str: str):
    try:
        dt_utc = dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_kst = dt_utc.astimezone(dt.timezone(dt.timedelta(hours=9)))
        return dt_kst.strftime("%Y%m%d%H%M%S"), dt_kst.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "", ""


def _format_views(n):
    return f"{int(n):,}" if isinstance(n, int) else "-"


def _parse_iso8601_duration_to_seconds(iso_dur: str) -> int:
    if not iso_dur or not iso_dur.startswith("PT"):
        return 0
    h = m = s = 0
    for part in re.findall(r"(\d+H|\d+M|\d+S)", iso_dur):
        if part.endswith("H"):
            h = int(part[:-1])
        elif part.endswith("M"):
            m = int(part[:-1])
        elif part.endswith("S"):
            s = int(part[:-1])
    return h * 3600 + m * 60 + s


def _fmt_hhmmss(total_sec: int) -> str:
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def _now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_iso_utc_datetime(date_str, hour, minute) -> str:
    kst = dt.timezone(dt.timedelta(hours=9))
    base = dt.datetime.strptime(date_str, "%Y-%m-%d")
    local_dt = dt.datetime(base.year, base.month, base.day, int(hour), int(minute), 0, tzinfo=kst)
    return local_dt.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_channel_id(youtube, channel_input: str) -> str:
    if not channel_input:
        return ""
    s = channel_input.strip()
    if _CHANNEL_ID_RE.match(s):
        return s
    if "youtube.com" in s:
        m = re.search(r"/channel/(UC[0-9A-Za-z_-]{22,})", s)
        if m:
            return m.group(1)
        m = re.search(r"/@([A-Za-z0-9._-]+)", s)
        if m:
            try:
                resp = youtube.channels().list(part="id", forHandle=m.group(1)).execute()
                items = resp.get("items", [])
                if items:
                    return items[0]["id"]
            except Exception:
                pass
    if s.startswith("@"):
        try:
            resp = youtube.channels().list(part="id", forHandle=s[1:]).execute()
            items = resp.get("items", [])
            if items:
                return items[0]["id"]
        except Exception:
            pass
    try:
        resp = youtube.channels().list(part="id", forUsername=s).execute()
        items = resp.get("items", [])
        if items:
            return items[0]["id"]
    except Exception:
        pass
    return ""


def search_youtube_videos_api(keyword, max_results=50, time_filter="any", custom_from="", custom_to="", duration_filter="any", sort_by="views", channel_filter=""):
    max_results = max(1, min(int(max_results), 50))
    api_key = _resolve_api_key()
    if not api_key:
        raise RuntimeError("YouTube API 키가 설정되지 않았습니다.")
    if build is None:
        raise RuntimeError("google-api-python-client가 필요합니다.")
    youtube = build("youtube", "v3", developerKey=api_key)

    params = {"q": keyword, "part": "snippet", "type": "video", "maxResults": min(max_results, 50)}
    if channel_filter:
        ch_id = _resolve_channel_id(youtube, channel_filter)
        if ch_id:
            params["channelId"] = ch_id

    now_utc = dt.datetime.now(dt.timezone(dt.timedelta(0)))
    if time_filter in ("day", "week", "month", "custom"):
        if time_filter == "day":
            params["publishedAfter"] = (now_utc - dt.timedelta(days=1)).isoformat()
        elif time_filter == "week":
            params["publishedAfter"] = (now_utc - dt.timedelta(weeks=1)).isoformat()
        elif time_filter == "month":
            params["publishedAfter"] = (now_utc - dt.timedelta(days=30)).isoformat()
        elif time_filter == "custom":
            if custom_from:
                params["publishedAfter"] = custom_from
            if custom_to:
                params["publishedBefore"] = custom_to
    if duration_filter in ("short", "medium", "long"):
        params["videoDuration"] = duration_filter
    params["order"] = "date" if sort_by == "date" else "viewCount"

    search_resp = youtube.search().list(**params).execute()
    video_ids = [it["id"]["videoId"] for it in search_resp.get("items", []) if it.get("id")]
    if not video_ids:
        return []

    videos_resp = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(video_ids)).execute()

    items = []
    for v in videos_resp.get("items", []):
        vid = v.get("id")
        sn = v.get("snippet", {}) or {}
        st = v.get("statistics", {}) or {}
        cd = v.get("contentDetails", {}) or {}
        title = (sn.get("title") or "").strip()
        url = f"https://www.youtube.com/watch?v={vid}" if vid else ""
        channel_title = (sn.get("channelTitle") or "").strip()
        channel_id = (sn.get("channelId") or "").strip()
        date_raw, date_fmt = _format_upload_datestr_iso8601_to_pair(sn.get("publishedAt") or "")
        dur_seconds = _parse_iso8601_duration_to_seconds(cd.get("duration") or "")
        try:
            vc = int(st.get("viewCount")) if "viewCount" in st else None
        except Exception:
            vc = None
        if title and url:
            items.append([url, title, date_raw, date_fmt, channel_title, vc, dur_seconds, channel_id])
    if sort_by == "views":
        items.sort(key=lambda x: (0 if isinstance(x[5], int) else 1, -(x[5] or 0), x[2] or "00000000"))
    else:
        items.sort(key=lambda x: x[2] or "00000000", reverse=True)
    return items[:max_results]


def _parse_rfc3339(ts: str) -> dt.datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return dt.datetime.fromisoformat(ts)


def _iso8601_to_seconds(dur: str) -> int:
    m = _ISO8601_DUR.fullmatch(dur)
    if not m:
        return 0
    h, m_, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + m_ * 60 + s


def _compute_window_iso(time_filter, custom_from_iso, custom_to_iso):
    if time_filter == "custom":
        after = custom_from_iso or "1970-01-01T00:00:00Z"
        before = custom_to_iso or _now_utc_iso()
    else:
        now = dt.datetime.now(dt.timezone.utc)
        after_dt = {
            "day": now - dt.timedelta(days=1),
            "week": now - dt.timedelta(weeks=1),
            "month": now - dt.timedelta(days=30),
        }.get(time_filter, dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc))
        after = after_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        before = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return after, before


def search_via_channel_uploads_fallback(api_key, keyword, channel_ids, published_after_iso, published_before_iso, max_results=50, sort_by="views"):
    if build is None:
        return []
    yt = build("youtube", "v3", developerKey=api_key)
    t_from = _parse_rfc3339(published_after_iso)
    t_to = _parse_rfc3339(published_before_iso)
    uploads_by_channel = {}
    for cid in channel_ids:
        try:
            ch = yt.channels().list(part="contentDetails,snippet", id=cid).execute()
            items = ch.get("items", [])
            if not items:
                continue
            uploads_by_channel[cid] = (
                items[0]["contentDetails"]["relatedPlaylists"]["uploads"],
                items[0]["snippet"].get("title", ""),
            )
        except Exception:
            continue

    cand_ids, meta = [], {}
    for cid, (uploads_pl, ch_title0) in uploads_by_channel.items():
        page_token = None
        keep = True
        while keep and len(cand_ids) < max_results:
            resp = yt.playlistItems().list(part="snippet,contentDetails", playlistId=uploads_pl, maxResults=50, pageToken=page_token).execute()
            for it in resp.get("items", []):
                vid = it["contentDetails"]["videoId"]
                pub_s = it["contentDetails"].get("videoPublishedAt") or it["snippet"]["publishedAt"]
                pub_t = _parse_rfc3339(pub_s)
                if pub_t < t_from:
                    keep = False
                    break
                if pub_t > t_to:
                    continue
                title = it["snippet"]["title"] or ""
                desc = it["snippet"].get("description") or ""
                ch_title = it["snippet"].get("channelTitle") or ch_title0 or ""
                if (keyword.lower() in title.lower()) or (keyword.lower() in desc.lower()):
                    cand_ids.append(vid)
                    meta[vid] = (title, ch_title, pub_s, cid)
                if len(cand_ids) >= max_results:
                    break
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    if not cand_ids:
        return []
    results = []
    for i in range(0, len(cand_ids), 50):
        chunk = cand_ids[i : i + 50]
        vr = yt.videos().list(part="contentDetails,statistics", id=",".join(chunk)).execute()
        for v in vr.get("items", []):
            vid = v["id"]
            title, ch_title, pub_s, ch_id = meta.get(vid, ("", "", "", ""))
            try:
                views = int(v.get("statistics", {}).get("viewCount", 0))
            except Exception:
                views = 0
            dur_s = _iso8601_to_seconds(v["contentDetails"]["duration"])
            url = f"https://www.youtube.com/watch?v={vid}"
            kst_dt = _parse_rfc3339(pub_s).astimezone(dt.timezone(dt.timedelta(hours=9)))
            date_fmt = kst_dt.strftime("%Y-%m-%d %H:%M")
            results.append((url, title, pub_s, date_fmt, ch_title, views, dur_s, ch_id))
    if sort_by == "views":
        results.sort(key=lambda x: x[5], reverse=True)
    else:
        results.sort(key=lambda x: x[2], reverse=True)
    return results[:max_results]
