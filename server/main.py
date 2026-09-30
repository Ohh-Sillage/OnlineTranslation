# 本地服务入口：接收扩展的 WebSocket 音频流 → VAD 分段 → ASR → 翻译 → 回传字幕
import asyncio
import json
import logging

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

import config
from asr import ASR
from translator import Translator
from vad import EnergyVAD

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ot-server")

app = FastAPI(title="OnlineTranslation Server", version="0.1.0")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "asr_model": config.MODEL_SIZE,
        "device": config.DEVICE,
        "translator": config.TRANSLATOR,
    }


async def handle_segment(ws: WebSocket, asr: ASR, translator: Translator, seg, lang: str):
    start_s, end_s, pcm = seg
    text = await asyncio.to_thread(asr.transcribe, pcm, lang)
    if not text:
        return
    try:
        translated = await asyncio.to_thread(translator.translate, text, lang)
    except Exception as exc:  # noqa: BLE001
        # 翻译接口异常时降级：仅显示原文，不让字幕流程中断
        logger.warning("翻译失败，降级为原文: %s", exc)
        translated = ""
    await ws.send_json({
        "type": "subtitle",
        "text": text,
        "translated": translated,
        "start": round(start_s, 2),
        "end": round(end_s, 2),
        "lang": lang,
    })
    logger.info("[%s] %s -> %s", lang, text[:40], translated[:40])


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    lang = config.DEFAULT_LANG
    vad = EnergyVAD()
    asr = ASR.instance()
    translator = Translator.instance()
    queue = asyncio.Queue(maxsize=100)
    stop = asyncio.Event()

    async def receiver():
        """接收二进制 PCM 与文本配置消息"""
        try:
            while not stop.is_set():
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    # 1000=正常关闭, 1006=页面/网络异常销毁（排查断开原因的关键）
                    logger.info("客户端断开 code=%s", msg.get("code"))
                    stop.set()
                    break
                data = msg.get("bytes")
                if data is not None:
                    await queue.put(np.frombuffer(data, dtype=np.float32))
                    continue
                text = msg.get("text")
                if text:
                    try:
                        cfg = json.loads(text)
                        if cfg.get("type") == "config" and cfg.get("lang"):
                            lang = cfg["lang"]
                            logger.info("客户端语言配置: %s", lang)
                    except (ValueError, TypeError):
                        pass
        except WebSocketDisconnect:
            stop.set()

    async def worker():
        """VAD 分段 → 识别 → 翻译 → 回传"""
        while not stop.is_set():
            try:
                data = await asyncio.wait_for(queue.get(), timeout=0.3)
                segs = vad.push(data)
            except asyncio.TimeoutError:
                segs = vad.flush()
            except Exception as exc:  # noqa: BLE001
                logger.error("音频处理异常: %s", exc)
                continue
            for seg in segs:
                try:
                    await handle_segment(ws, asr, translator, seg, lang)
                except WebSocketDisconnect:
                    stop.set()
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.warning("识别/翻译异常: %s", exc)
                    try:
                        await ws.send_json({"type": "error", "message": str(exc)})
                    except Exception:  # noqa: BLE001
                        stop.set()
                        break

    try:
        await asyncio.gather(receiver(), worker())
    except WebSocketDisconnect:
        pass
    finally:
        stop.set()
        logger.info("客户端断开")


if __name__ == "__main__":
    import uvicorn

    print(f"本地服务启动: http://{config.HOST}:{config.PORT}  (模型: {config.MODEL_SIZE}, 翻译: {config.TRANSLATOR})")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
