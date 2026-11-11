"""Editable, asset-free collage/slideshow/title templates for the timeline."""
import copy,math,textwrap
from pathlib import Path
import video_project as vp
PRESETS=[('collage2','Kolase 2 foto • berdampingan'),('collage4','Kolase 4 foto • 2×2'),('collage6','Kolase 6 foto • 3×2'),('collage9','Kolase 9 foto • 3×3'),('slideshow','Slideshow foto • gerak zoom halus'),('opening','Opening video • judul & logo'),('ending','Ending video • penutup & logo'),('lowerthird','Lower third • nama / keterangan'),('quote','Kartu kutipan / ucapan')]
IMAGE_EXT={'.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'}
def apply_template(project,preset,photos=(),title='',subtitle='',duration=4.,placement='append',playhead=0.,logo='',background='#101827'):
    if preset not in dict(PRESETS):raise ValueError('Template tidak dikenal.')
    if placement not in ('append','prepend','playhead'):raise ValueError('Posisi template tidak sah.')
    vp.numeric(duration,.5,60,'Durasi template');vp.numeric(playhead,0,86400,'Playhead');vp.color(background)
    if len(photos)>100:raise ValueError('Maksimum 100 foto per pembuatan template; batas total proyek 128 klip.')
    if len(title)>300 or len(subtitle)>2000:raise ValueError('Teks template terlalu panjang.')
    paths=[str(Path(p).resolve()) for p in photos]
    if logo:logo=str(Path(logo).resolve())
    for path in paths+([logo] if logo else []):
        if Path(path).suffix.lower() not in IMAGE_EXT or not Path(path).is_file():raise ValueError('Pilih file foto PNG/JPEG/BMP/WebP/TIFF yang tersedia.')
    if (preset.startswith('collage') or preset=='slideshow') and not paths:raise ValueError('Pilih foto terlebih dahulu.')
    p=copy.deepcopy(project);duration=max(1/vp.fps(p),vp.snap(p,duration));tracks=[vp.new_track('Template • Latar','visual'),vp.new_track('Template • Foto/logo','visual'),vp.new_track('Template • Teks','visual')];clips=[]
    def add(layer,kind,length,**values):
        c=vp.new_clip(tracks[layer]['id'],kind,duration=length,**values);clips.append(c);return c
    def fade(length):return min(.4,length/5)
    def title_clip(text,y,height,size,length):return add(2,'text',length,name=text[:60] or 'Teks template',text=text,color='#ffffff',x=5,y=y,width=90,height=height,font_size=size,fade_in=fade(length),fade_out=fade(length))
    def wrapped(text,width):return '\n'.join(textwrap.fill(line,width) for line in text.splitlines())
    if preset.startswith('collage'):
        columns,rows={'collage2':(2,1),'collage4':(2,2),'collage6':(3,2),'collage9':(3,3)}[preset];count=columns*rows;pages=math.ceil(len(paths)/count);length=duration*pages;gap=2.;cw=(100-(columns+1)*gap)/columns;ch=(100-(rows+1)*gap)/rows
        add(0,'color',length,name='Latar kolase',color=background,fit='stretch')
        for i,path in enumerate(paths):
            page,cell=divmod(i,count);row,col=divmod(cell,columns);add(1,'image',duration,path=path,name=Path(path).name,start=page*duration,x=gap+col*(cw+gap),y=gap+row*(ch+gap),width=cw,height=ch,fit='cover',fade_in=fade(duration),fade_out=fade(duration))
        if title:title_clip(wrapped(title,45),2,15,4,length)
    elif preset=='slideshow':
        length=len(paths)*duration;add(0,'color',length,name='Latar slideshow',color=background,fit='stretch')
        for i,path in enumerate(paths):
            c=add(1,'image',duration,path=path,name=Path(path).name,start=i*duration,fit='cover',fade_in=fade(duration),fade_out=fade(duration));c['keyframes']=[{'time':0.,**{key:c[key] for key in vp.KEYS}},{'time':duration,**{key:c[key] for key in vp.KEYS},'scale':1.06,'x':-3.,'y':-3.}]
        if title:title_clip(wrapped(title,45),78,20,4,length)
    elif preset=='lowerthird':
        length=duration;add(0,'color',length,name='Panel lower third',color=background,opacity=.9,x=4,y=74,width=92,height=22,fit='stretch',fade_in=fade(length),fade_out=fade(length));title_clip(wrapped(title or 'Nama pembicara',45),74,12,4.5,length)
        if subtitle:title_clip(wrapped(subtitle,65),85,10,2.8,length)
    else:
        length=duration;add(0,'color',length,name='Latar '+preset,color=background,fit='stretch')
        if paths:add(1,'image',length,path=paths[0],name='Foto latar',fit='cover',opacity=.3,fade_in=fade(length),fade_out=fade(length))
        if preset=='quote':
            title_clip(wrapped(title or 'Setiap momen memiliki cerita.',34),16,58,6,length)
            if subtitle:title_clip(wrapped(subtitle,55),76,15,3,length)
        else:
            title_clip(wrapped(title or ('Terima kasih' if preset=='ending' else 'Judul video'),32),32,30,7,length)
            if subtitle:title_clip(wrapped(subtitle,55),61,21,3.5,length)
            if logo:add(1,'image',length,path=logo,name='Logo',x=40,y=7,width=20,height=22,fit='contain',fade_in=fade(length),fade_out=fade(length))
    offset=vp.snap(p,0 if placement=='prepend' else vp.duration(p) if placement=='append' else playhead)
    if placement=='prepend':
        locked={t['id'] for t in p['tracks'] if t['locked']}
        if any(c['track'] in locked for c in p['clips']):raise ValueError('Buka kunci layer sebelum menyisipkan opening di awal.')
        for c in p['clips']:c['start']+=length
    for c in clips:c['start']=vp.snap(p,c['start']+offset)
    index=next((i for i,t in enumerate(p['tracks']) if t['kind']=='subtitle' or t['name']=='Judul' or any(c['track']==t['id'] and c['kind']=='text' for c in p['clips'])),len(p['tracks']))
    p['tracks'][index:index]=tracks;p['clips'].extend(clips);vp.validate(p,sources=True);project.clear();project.update(p)
    return {'track':tracks[1]['id'],'clips':[c['id'] for c in clips],'duration':length,'start':offset,'end':offset+length}
