from PIL import Image, ImageDraw, ImageFilter
S = 4320; C = S//2
CREAM=(244,237,225); INK=(17,17,17); ACID=(208,255,52); RED=(196,66,38); GREEN=(92,110,50); GOLD=(232,170,60); PINK=(255,56,106); PLATE=(250,247,240)
img = Image.new("RGB",(S,S),CREAM)
d = ImageDraw.Draw(img)
# right half dark with hazard stripes
d.rectangle((C,0,S,S),fill=INK)
band=150
stripes = Image.new("RGB",(S,S),INK); sd=ImageDraw.Draw(stripes)
x=-S
while x<S*2:
    sd.polygon([(x,S),(x+band,S),(x+band+S,0),(x+S,0)],fill=ACID); x+=band*2
# stripes only in a ring band near edges of the right half (frame), keep centre calm
mask = Image.new("L",(S,S),0); md=ImageDraw.Draw(mask)
md.rectangle((C,0,S,S),fill=255)
md.ellipse((C-int(S*0.40),C-int(S*0.40),C+int(S*0.40),C+int(S*0.40)),fill=0)
img.paste(stripes,(0,0),mask)
d = ImageDraw.Draw(img)
d.rectangle((C-20,0,C+20,S),fill=INK)  # crisp divider
# plate shadow
R=int(S*0.275)
sh = Image.new("L",(S,S),0); ImageDraw.Draw(sh).ellipse((C-R+60,C-R+110,C+R+60,C+R+110),fill=150)
sh = sh.filter(ImageFilter.GaussianBlur(70))
img.paste((0,0,0),(0,0),sh)
d = ImageDraw.Draw(img)
d.ellipse((C-R,C-R,C+R,C+R),fill=PLATE)
r2=int(R*0.78); d.ellipse((C-r2,C-r2,C+r2,C+r2),fill=(236,230,218))
# right half of plate: sludge with hex nuts
import math
sl = Image.new("RGBA",(S,S),(0,0,0,0)); sd2=ImageDraw.Draw(sl)
fr0=int(r2*0.82)
sd2.ellipse((C-fr0,C-fr0,C+fr0,C+fr0),fill=(150,190,40,255))
sd2.ellipse((C+int(fr0*0.05),C-int(fr0*0.6),C+int(fr0*0.6),C-int(fr0*0.1)),fill=(185,225,60,255))
def hexnut(cx,cy,rr):
    pts=[(cx+rr*math.cos(math.radians(60*k+30)),cy+rr*math.sin(math.radians(60*k+30))) for k in range(6)]
    sd2.polygon(pts,fill=(120,124,132,255)); ri=int(rr*0.45); sd2.ellipse((cx-ri,cy-ri,cx+ri,cy+ri),fill=(150,190,40,255))
hexnut(C+int(fr0*0.45),C+int(fr0*0.3),int(fr0*0.22))
hexnut(C+int(fr0*0.22),C-int(fr0*0.35),int(fr0*0.15))
sd2.ellipse((C+int(fr0*0.55)-60,C-int(fr0*0.15)-60,C+int(fr0*0.55)+60,C-int(fr0*0.15)+60),fill=PINK+(255,))
rm = Image.new("L",(S,S),0); ImageDraw.Draw(rm).rectangle((C+20,0,S,S),fill=255)
sl.putalpha(Image.composite(sl.split()[3], Image.new("L",(S,S),0), rm)); img.paste(sl,(0,0),sl)
d = ImageDraw.Draw(img)
# left half: food - sauce blob + toppings, clipped to left of plate well
food = Image.new("RGBA",(S,S),(0,0,0,0)); fd=ImageDraw.Draw(food)
fr=int(r2*0.82)
fd.ellipse((C-fr,C-fr,C+fr,C+fr),fill=RED+(255,))
fd.ellipse((C-int(fr*0.55),C-int(fr*0.62),C+int(fr*0.1),C-int(fr*0.05)),fill=GOLD+(255,))
for (dx,dy,rr,col) in [(-0.62,0.25,0.16,GREEN),(-0.35,0.55,0.13,GREEN),(-0.72,-0.25,0.11,GOLD),(-0.25,0.15,0.12,(150,40,30)),(-0.5,-0.55,0.09,GREEN)]:
    cx,cy,rrr=C+int(dx*fr),C+int(dy*fr),int(rr*fr); fd.ellipse((cx-rrr,cy-rrr,cx+rrr,cy+rrr),fill=col+(255,))
fm = Image.new("L",(S,S),0); ImageDraw.Draw(fm).rectangle((0,0,C-20,S),fill=255)
alpha = Image.composite(food.split()[3], Image.new("L",(S,S),0), fm)
food.putalpha(alpha); img.paste(food,(0,0),food)
d = ImageDraw.Draw(img)
d.rectangle((C-20,C-R,C+20,C+R),fill=INK)  # divider through plate
# fork (left)
fx=C-int(S*0.345); top=C-int(S*0.20); bot=C+int(S*0.22); w=95
d.rounded_rectangle((fx-w//2,top+520,fx+w//2,bot),radius=w//2,fill=INK)
d.rounded_rectangle((fx-210,top+300,fx+210,top+600),radius=120,fill=INK)
for i in range(4):
    tx=fx-180+i*120; d.rounded_rectangle((tx-34,top,tx+34,top+420),radius=34,fill=INK)
# spanner (right)
wx=C+int(S*0.345)
d.rounded_rectangle((wx-w//2-10,top+380,wx+w//2+10,bot),radius=w,fill=ACID)
hr=230; d.ellipse((wx-hr,top-40,wx+hr,top-40+2*hr),fill=ACID)
d.rectangle((wx-85,top-60,wx+85,top+170),fill=INK)
d.ellipse((wx-hr//2+40,bot-hr+40,wx+hr//2-40,bot+hr//2-80),fill=ACID)
img = img.resize((1080,1080),Image.LANCZOS)
img.save("yummers-grubbers-profile.png")
# circle preview
prev = img.copy().resize((320,320),Image.LANCZOS); m=Image.new("L",(320,320),0); ImageDraw.Draw(m).ellipse((0,0,319,319),fill=255)
bg=Image.new("RGB",(760,360),(0,0,0)); bg.paste(prev,(20,20),m)
small=img.resize((110,110),Image.LANCZOS); m2=Image.new("L",(110,110),0); ImageDraw.Draw(m2).ellipse((0,0,109,109),fill=255)
bg.paste(small,(400,125),m2); s3=img.resize((56,56),Image.LANCZOS); m3=Image.new("L",(56,56),0); ImageDraw.Draw(m3).ellipse((0,0,55,55),fill=255); bg.paste(s3,(560,152),m3)
bg.save("preview.png")
