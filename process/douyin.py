import asyncio
import json
import logging
import os
import time

from process.download import Download
from process.douyin_downloader_playwright_v6 import get_aweme_detail
from .result import Result


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
douyin_logger = logging.getLogger("DouYin")


def handle_aweme_download(share_url, base_path="downloads"):
    """抖音专用下载入口，成功返回保存目录字符串，失败抛异常。"""
    result_handler = Result()
    downloader = Download(
        thread=1,
        music=True,
        cover=True,
        avatar=True,
        resjson=True,
        folderstyle=False,
    )

    douyin_logger.info("[提示] 正在请求单个作品")

    max_retries = 3
    retry_count = 0
    last_error = ""

    while retry_count < max_retries:
        try:
            douyin_logger.info(f"[提示] 第 {retry_count + 1} 次尝试获取作品信息")

            aweme_data = asyncio.run(get_aweme_detail(share_url))
            if not aweme_data:
                last_error = "aweme_detail 为空"
                raise RuntimeError(last_error)

            raw = json.dumps(aweme_data, ensure_ascii=False)
            datadict = json.loads(raw)
            result_handler.dataConvert(0, result_handler.awemeDict, datadict)
            datanew = result_handler.awemeDict

            if not datanew:
                last_error = "数据转换后为空"
                raise RuntimeError(last_error)

            video_url_list = datanew.get("video", {}).get("play_addr", {}).get("url_list", [])
            if not video_url_list:
                last_error = "未获取到 video_url"
                raise RuntimeError(last_error)

            aweme_path = str(base_path)
            os.makedirs(aweme_path, exist_ok=True)

            downloader.userDownload(awemeList=[datanew], savePath=aweme_path)
            douyin_logger.info("[成功] 抖音视频下载完成")
            return aweme_path

        except Exception as e:
            last_error = str(e)
            retry_count += 1
            douyin_logger.error(f"[错误] 抖音解析失败: {last_error}")
            if retry_count < max_retries:
                douyin_logger.info("[提示] 等待 5 秒后重试...")
                time.sleep(5)

    douyin_logger.error("[失败] 已达到最大重试次数，无法下载抖音视频")
    raise RuntimeError(f"抖音专用解析失败: {last_error or '未知错误'}")
