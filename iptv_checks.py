"""Packaged IPTV acceptance against a local HTTP station, no private/premium TV."""
import json,subprocess,threading,time,uuid
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
import imageio_ffmpeg
from core import Cue
from internet_tv import parse_m3u
from video_render import flags

def wait(predicate,timeout=35):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        QApplication.processEvents()
        if predicate():return
        time.sleep(.03)
    raise RuntimeError('IPTV acceptance timed out')
def run_iptv_checks(owner,root):
    root=Path(root);ff=imageio_ffmpeg.get_ffmpeg_exe();source=root/'station.mp4'
    subprocess.run([ff,'-v','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=5:duration=18','-f','lavfi','-i','sine=frequency=440:duration=18','-c:v','libx264','-preset','ultrafast','-c:a','aac','-movflags','+faststart','-shortest',str(source)],check=True,**flags())
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root),**kwargs)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
    privacy_marker='cyber80-private-fixture-'+uuid.uuid4().hex
    tv=owner.open_internet_tv();key=owner.key.text()
    wait(lambda:tv.job is None and bool(tv.rows))
    assert tv.bundled.is_file() and len(tv.rows)>100
    try:
        rows=parse_m3u(f'#EXTM3U\n#EXTINF:-1 tvg-id="fixture.id" tvg-country="ID" group-title="News",Local station\n{base}/station.mp4?privacy_check={privacy_marker}\n#EXTINF:-1 group-title="18+",Age restricted fixture\n{base}/station.mp4?age=18\n')
        tv.got_rows(rows);assert len(tv.visible_rows)==1;tv.table.selectRow(0);tv.play()
        wait(lambda:tv.preview.player.get_time()>300)
        assert tv.preview.player is owner.player and owner.path=='' and owner.stream_url==rows[0]['url']
        owner.audio_panel.boost_preset(6);wait(lambda:owner.pending_seek is None and owner.player.get_time()>100)
        assert owner.stream_url==rows[0]['url']
        owner.audio_panel.boost_preset(0);wait(lambda:owner.pending_seek is None and owner.player.get_time()>100)
        owner.toggle_pip();wait(lambda:owner.pip is not None and owner.pending_seek is None);owner.pip.close();wait(lambda:owner.pip is None and owner.pending_seek is None)
        assert owner.stream_url==rows[0]['url']
        assert not owner._native_log_enabled
        assert privacy_marker not in owner.log_path.read_text(encoding='utf-8',errors='replace')
        owner.key.setText('synthetic-fixture-no-real-key')
        with patch('live_tv_subtitles.transcribe',return_value=[Cue(0,14,'Test speech','Subtitle Indonesia','en')]) as api:
            tv.start_subtitles();wait(lambda:bool(tv.caption_queue),45);wait(lambda:tv.caption_label.text()=='Subtitle Indonesia');assert api.call_count>=1
            tv.stop_subtitles();wait(lambda:tv.caption_job is None)
        tv.lock.unlocked=True;tv.got_rows(rows);assert len(tv.visible_rows)==2;tv.relock();assert len(tv.visible_rows)==1 and tv.preview.released
        return {'online_native_logs_disabled':'PASS','pip_close_button_returns_to_player':'PASS','shared_full_player_engine':'PASS','eq_renderer_restart_preserves_online_source':'PASS','online_pip_preserves_source':'PASS','bundled_catalog_auto_load':'PASS','m3u_http_station_playback':'PASS','continuous_ffmpeg_audio_capture':'PASS','translated_caption_display':'PASS_MOCK_STT_NO_NETWORK_API','parental_default_lock_relock':'PASS','live_gemini_on_public_station':'NOT_RUN_NO_CREDENTIAL','public_catalog_availability':'NOT_GUARANTEED'}
    finally:
        owner.key.setText(key);tv.stop_subtitles()
        if tv.caption_job:wait(lambda:tv.caption_job is None)
        tv.close();server.shutdown();server.server_close()
