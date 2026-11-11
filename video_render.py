"""Offline FFmpeg composition shared by editor still previews, proxy and final export."""
import copy,math,os,re,subprocess,tempfile,uuid,shutil
from pathlib import Path
import video_project as vp

def flags():return {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
def probe(ff,path):
    path=Path(path).resolve()
    if not path.is_file():raise ValueError('Sumber tidak ditemukan.')
    r=subprocess.run([ff,'-hide_banner','-i',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',timeout=25,**flags())
    text=r.stderr;video=bool(re.search(r'Stream .*Video:',text));audio=bool(re.search(r'Stream .*Audio:',text));image=path.suffix.lower() in ('.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff')
    if not (video or audio):raise ValueError('Format tidak dapat dibaca: '+path.name)
    match=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',text);length=int(match[1])*3600+int(match[2])*60+float(match[3]) if match else 0
    if not image and length<=0:raise ValueError('Durasi sumber belum tersedia: '+path.name)
    return {'path':str(path),'kind':'image' if image else 'video' if video else 'audio','duration':5. if image else length,'has_audio':audio,'name':path.name}
def expression(c,key,var='t'):
    rows=sorted(c['keyframes'],key=lambda k:k['time'])
    if not rows:return f'{c[key]:.9g}'
    result=f'{rows[-1][key]:.9g}'
    for a,b in reversed(list(zip(rows,rows[1:]))):
        piece=f"({a[key]:.9g}+({b[key]-a[key]:.9g})*({var}-{a['time']:.9g})/{b['time']-a['time']:.9g})"
        result=f"if(lt({var},{b['time']:.9g}),{piece},{result})"
    return f"if(lt({var},{rows[0]['time']:.9g}),{rows[0][key]:.9g},{result})"
def tempo(speed):
    result=[]
    while speed>2:result.append('atempo=2');speed/=2
    while speed<.5:result.append('atempo=0.5');speed/=.5
    result.append(f'atempo={speed:.9g}');return ','.join(result)
def escaped(path):return str(path).replace('\\','/').replace(':','\\:').replace("'","\\'")
def font():
    options=[Path(os.environ.get('SystemRoot',r'C:\Windows'))/'Fonts'/'arial.ttf',Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    return next((p for p in options if p.is_file()),None)
def for_still(p,t):
    result=copy.deepcopy(p);result['clips']=[];frame=1/vp.fps(p)
    for c in p['clips']:
        if c['start']<=t<c['start']+c['duration'] and c['kind']!='audio':
            cc=vp.slice_clip(c,t,min(c['start']+c['duration'],t+frame));cc['start']=0;cc['duration']=max(frame,cc['duration']);cc['keyframes']=[{'time':0,**{key:vp.value_at(c,key,t-c['start']) for key in vp.KEYS}}]
            envelope=min(1,(t-c['start'])/c['fade_in'] if c['fade_in'] else 1,(c['start']+c['duration']-t)/c['fade_out'] if c['fade_out'] else 1);cc['keyframes'][0]['opacity']*=max(0,envelope)
            result['clips'].append(cc)
    # Keep a frame even at an empty gap.
    return result

def command(ff,p,target,work,mode='CPU',preview=False,still=None):
    vp.validate(p,sources=True);original=p;p=for_still(p,still) if still is not None else copy.deepcopy(p);s=p['settings'];w,h=int(s['width']),int(s['height'])
    if preview or still is not None:
        factor=min(1,640/w,360/h);w=max(64,int(w*factor)//2*2);h=max(64,int(h*factor)//2*2)
    length=max(1/vp.fps(p),vp.duration(p));work=Path(work);inputs=[];graph=[];visual='base';audio=[];index=0;layer=0
    graph.append(f"color=c={vp.color(s['background'])}:s={w}x{h}:r={s['fps']}:d={length:.9g},format=rgba[base]")
    solo=any(t['solo'] for t in p['tracks']);tracks={t['id']:t for t in p['tracks']}
    for track in p['tracks']:
        clips=sorted((c for c in p['clips'] if c['track']==track['id']),key=lambda c:c['start'])
        for c in clips:
            visible=c['kind']!='audio' and not track['hidden'];audible=(c['kind']=='audio' or c['kind']=='video' and c['has_audio']) and not track['muted'] and (not solo or track['solo']) and still is None
            if not visible and not audible:continue
            start=c['start'];dur=c['duration'];end=start+dur
            if c['kind']=='subtitle':
                if not visible:continue
                from core import parse_srt,Cue,srt
                cues=[]
                for cue in parse_srt(c['text']):
                    a=max(0,(cue.start-c['in'])/c['speed']);b=min(dur,(cue.end-c['in'])/c['speed'])
                    if b>a:cues.append(Cue(start+a,start+b,cue.source,cue.target))
                sub=work/f'subtitle-{layer}.srt';sub.write_text(srt(cues,True),encoding='utf-8');out=f'layer{layer}';layer+=1
                graph.append(f"[{visual}]subtitles=filename='{sub.name}':force_style='FontSize={c['font_size']*2.88:.3f},Outline=2,Alignment=2'[{out}]");visual=out;continue
            vlabel=None
            if c['kind'] in ('video','image','audio'):
                inputs+=['-threads','1']
                if c['kind']=='image':inputs+=['-loop','1','-framerate',str(s['fps']),'-t',f'{dur:.9g}']
                else:inputs+=['-ss',f"{c['in']:.9g}",'-t',f'{dur*c["speed"]:.9g}']
                inputs+=['-i',c['path']];source=index;index+=1
                if visible:vlabel=f'{source}:v:0'
                if audible:
                    alabel=f'a{len(audio)}';af=[f'atrim=duration={dur*c["speed"]:.9g}','asetpts=PTS-STARTPTS',tempo(c['speed']),f'atrim=duration={dur:.9g}','aresample=48000','aformat=sample_fmts=fltp:channel_layouts=stereo',f"volume='pow(10,(({expression(c,'volume')})+{track['volume']:.9g})/20)':eval=frame"]
                    if c['pan']:af.append(f"pan=stereo|c0={1-max(0,c['pan']):.9g}*c0|c1={1+min(0,c['pan']):.9g}*c1")
                    if c['fade_in']:af.append(f"afade=t=in:st=0:d={c['fade_in']:.9g}")
                    if c['fade_out']:af.append(f"afade=t=out:st={dur-c['fade_out']:.9g}:d={c['fade_out']:.9g}")
                    af.append(f'adelay={round(start*1000)}|{round(start*1000)}');graph.append(f'[{source}:a:0]'+','.join(af)+f'[{alabel}]');audio.append((alabel,track['kind']))
            elif visible and c['kind'] in ('color','text'):
                vlabel=f'generated{layer}'
                graph.append(f"color=c={vp.color(c['color']) if c['kind']=='color' else 'black@0'}:s={w}x{h}:r={s['fps']}:d={dur:.9g},format=rgba[{vlabel}]")
            if visible and vlabel is not None:
                vl=f'visual{layer}';out=f'layer{layer}';layer+=1;filters=[f'setpts=(PTS-STARTPTS)/{c["speed"] if c["kind"]=="video" else 1:.9g}',f'fps={s["fps"]}',f'trim=duration={dur:.9g}','setsar=1','format=rgba']
                if c['rotation']==90:filters.append('transpose=1')
                elif c['rotation']==180:filters+=['hflip','vflip']
                elif c['rotation']==270:filters.append('transpose=2')
                bw=max(2,round(w*c['width']/100)//2*2);bh=max(2,round(h*c['height']/100)//2*2)
                fit=c.get('fit','contain')
                if fit=='stretch':filters.append(f'scale={bw}:{bh}:flags=bicubic')
                elif fit=='cover':filters+= [f'scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=bicubic',f'crop={bw}:{bh}']
                else:filters += [f'scale={bw}:{bh}:force_original_aspect_ratio=decrease:flags=bicubic',f'pad={bw}:{bh}:(ow-iw)/2:(oh-ih)/2:color=black@0']
                if c['kind']=='text':
                    text=work/f'title-{layer}.txt';text.write_text(c['text'],encoding='utf-8');face=font()
                    if face is None:raise ValueError('Font sistem Arial/DejaVu Sans tidak ditemukan.')
                    filters.append(f"drawtext=fontfile='{escaped(face)}':textfile='{text.name}':expansion=none:fontcolor={vp.color(c['color'])}:fontsize={max(6,round(h*c['font_size']/100))}:x=(w-tw)/2:y=(h-th)/2:box=1:boxcolor=black@0.3:boxborderw=5")
                if c['brightness'] or c['contrast']!=1 or c['saturation']!=1:filters.append(f"eq=brightness={c['brightness']:.9g}:contrast={c['contrast']:.9g}:saturation={c['saturation']:.9g},format=rgba")
                if c.get('chroma'):filters.append(f"chromakey={vp.color(c['chroma_color'])}:{c['chroma_similarity']:.9g}:{c['chroma_blend']:.9g},format=rgba")
                if c.get('blur',0):filters.append(f"gblur=sigma={c['blur']:.9g}")
                scale=expression(c,'scale');filters.append(f"scale=w='max(2,trunc({bw}*({scale})/2)*2)':h='max(2,trunc({bh}*({scale})/2)*2)':eval=frame")
                if c['keyframes'] and len({k['opacity'] for k in c['keyframes']})>1:
                    alpha=expression(c,'opacity','T');filters.append(f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({alpha})'")
                else:filters.append(f"colorchannelmixer=aa={vp.value_at(c,'opacity',0):.9g}")
                if c['fade_in']:filters.append(f"fade=t=in:st=0:d={c['fade_in']:.9g}:alpha=1")
                if c['fade_out']:filters.append(f"fade=t=out:st={dur-c['fade_out']:.9g}:d={c['fade_out']:.9g}:alpha=1")
                filters.append(f'setpts=PTS+{start:.9g}/TB');graph.append(f'[{vlabel}]'+','.join(filters)+f'[{vl}]')
                x=expression(c,'x',f'(t-{start:.9g})');y=expression(c,'y',f'(t-{start:.9g})')
                graph.append(f"[{visual}][{vl}]overlay=x='{w}/100*({x})':y='{h}/100*({y})':enable='gte(t,{start:.9g})*lt(t,{end:.9g})':eof_action=pass:repeatlast=0:format=auto[{out}]");visual=out
    graph.append(f'[{visual}]format=yuv420p[vout]')
    if still is None:
        def bus(labels,name):
            chain=''.join('['+x+']' for x in labels)+(f'amix=inputs={len(labels)}:duration=longest:normalize=0' if len(labels)>1 else 'anull')+f',apad=whole_dur={length:.9g},atrim=duration={length:.9g}[{name}]';graph.append(chain);return name
        if s.get('ducking') and any(k=='voice' for _,k in audio) and any(k=='music' for _,k in audio):
            voice=bus([a for a,k in audio if k=='voice'],'voicebus');music=bus([a for a,k in audio if k=='music'],'musicbus');graph.append(f'[{voice}]asplit=2[voicefinal][side]');graph.append(f'[{music}][side]sidechaincompress=threshold=0.03:ratio=6:attack=10:release=400[ducked]');labels=['voicefinal','ducked']+[a for a,k in audio if k not in ('voice','music')]
        else:labels=[a for a,_ in audio]
        if labels:final=bus(labels,'mixed');graph.append(f'[{final}]alimiter=limit=0.95:level=false[aout]')
        else:graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={length:.9g}[aout]')
    script=work/'composition.ffgraph';script.write_text(';\n'.join(graph),encoding='utf-8');args=[ff,'-hide_banner','-v','error','-y',*inputs,'-filter_complex_threads','1','-filter_complex_script',str(script),'-map','[vout]']
    if still is not None:args+=['-an','-frames:v','1','-c:v','png','-update','1']
    else:
        enc={'CPU':['-c:v','libx264','-preset','ultrafast' if preview else 'medium','-crf','28' if preview else '20'],'NVIDIA NVENC':['-c:v','h264_nvenc','-cq','20'],'Intel QSV':['-c:v','h264_qsv','-global_quality','20'],'AMD AMF':['-c:v','h264_amf','-quality','quality']}[mode]
        args+=['-map','[aout]',*enc,'-threads','4','-c:a','aac','-b:a','192k','-r',str(s['fps']),'-t',f'{length:.9g}','-movflags','+faststart']
    args+=['-progress','pipe:1','-nostats',str(target)]
    if os.name=='nt' and len(subprocess.list2cmdline(args))>30000:raise ValueError('Proyek melebihi batas perintah Windows. Kurangi jumlah klip atau pendekkan path sumber.')
    return args

def render(ff,p,target,mode='CPU',preview=False,still=None,cancelled=lambda:False,progress=lambda t:None,process=lambda p:None):
    target=Path(target).resolve();sources={Path(c['path']).resolve() for c in p['clips'] if c['kind'] in ('video','image','audio')}
    if target in sources:raise ValueError('Hasil tidak boleh menimpa sumber.')
    def stamp():
        try:s=target.stat();return s.st_size,s.st_mtime_ns
        except FileNotFoundError:return None
    before=stamp();target.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(target.parent).free<64*1024*1024:raise ValueError('Ruang disk kurang dari 64 MiB.')
    temp=target.with_name(target.stem+'.'+uuid.uuid4().hex+'.partial'+target.suffix);proc=None
    try:
        with tempfile.TemporaryDirectory(prefix='cyber80-compose-') as work,tempfile.TemporaryFile() as errors:
            args=command(ff,p,temp,work,mode,preview,still)
            if cancelled():raise InterruptedError('Dibatalkan')
            proc=subprocess.Popen(args,cwd=work,stdout=subprocess.PIPE,stderr=errors,text=True,**flags());process(proc)
            for line in proc.stdout:
                if cancelled():proc.kill();break
                if line.startswith('out_time_us='):
                    try:progress(int(line.split('=')[1])/1e6)
                    except ValueError:pass
            proc.wait()
            if cancelled():raise InterruptedError('Render dibatalkan')
            if proc.returncode:
                errors.seek(0);detail=errors.read().decode(errors='replace')[-2500:]
                for path in sources:detail=detail.replace(str(path),path.name)
                raise RuntimeError('Komposisi FFmpeg gagal. Periksa sumber/encoder. '+detail)
        if stamp()!=before:raise ValueError('File tujuan berubah selama render; hasil final tidak diganti.')
        os.replace(temp,target);return str(target)
    finally:
        process(None)
        if proc:
            if proc.poll() is None:proc.kill();proc.wait()
            if proc.stdout:proc.stdout.close()
        temp.unlink(missing_ok=True)
