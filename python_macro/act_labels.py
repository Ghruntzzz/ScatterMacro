"""Act button OCR-free matching from the user-supplied Story act screenshot.

The reference contains only the short number/symbol label strips, explicitly
excluding the decorative star rows. Supports button appearance at nearby scales.
"""
import base64
import zlib

import cv2
import numpy as np

_ATLAS = "c-rlk?N3`(7{E_ocyXf}uVtpRTzX$Aw7sV-g;tOih%P{(R0+BP0!BAqkc^3L3tJtUOurxzlxRjY#%Rnm%UqF#IG(W>qaTbP{WpyNKs~o*ruVk@v@z8g<L^tKJondgZ*HHb=Q+#EMR2hgUN45FVpz;&ZhT&oS<v!|2cgPIb#7k6i_RlEzhkUUzNF?%Q^U`x)P$hUzMv*t{c9?fdWu(PpI0NxDMjMc*=N<nO{4upV%6DM4TA^~$*E30qoq%gTGY8oEfGax)VY&ddWkf_sB;rq2GB3R$)Y+po<l7{<tNmsCvu2KdPg*=v0@k{#L|q8j*R3B3DM|C#v&J@BbiunvchO|m`Jg)czi6Dxe|-V<LWRvJmfDKfs&E4w2N;mba$~5A@q<$btGft)7_7|jV_vWC;)^z?kbAYhTeyd2Dac`<kpvXbQ^k56q1Nn<$c*m=={3%&?a0*l24y{gxF62X3dx)G3eBH010zhyDE*d@t9`d-rgJGPFtBbJFohNfRf+;puB{eNYGu$g)Z+Y&fYo_u`Z4101KwzVx0t5vyQCrXOIbTPAHRS&%9Nv#Q8#5_5}hRorI2nQl=e25(YbzO1mEt4f}&#;Yc(Z35Pm^!Ol?kV05TE)J3izgu#GM{%hr1GCZP)3n*?2dD{jnRm0`dYV!J$<tR;Rs!1xp?}m}1NY(wYJ3bB2YW3^acvHo5L;g{KKm(<EeKtfCST?d0=V3GIAvOMinIegX`IR~Y1_)Aa#~YHccKkGe$LiDV7O&})@&;hj$Wn^eVHn=p`TWe`YFdS3rkwmN#zq<EsqrjCmiK6LGA@SyyG4svaQh@traCTD`rpY+-Ci1m<TARJ<gGNRat^*m0FhcsBY4mntPrWMmQv$R^KBR}Bw5=5q(V~Fc)EP)l4ZCE$$_j6ha*=~m!N33)umrSfl?LGwQZ-hP(fEAWNM{%3qj!A|CMg>KUlE9ahyPZ3QuJ*?ZVt3^|a$WMxC-|(pA^lK$A=t;KNYJZ*c0j6zQoASe4396K!vi&{y{WzG$zIDH4yA=Z0Gr2St)mU7TqH2-j0@x3Kxx6zNbaMQX16R=M4}fuppPyPSLLn;Ykk9HmxsdyRqY`SsocMepW$55@&sN{5nki<itLfgmB^S7g#7!C*&v3%DO*#VJ*{Jm7JyAU>DV(JXj{W{1<|({p&=%*x_%d+)h7XZ^g6)#f>SVfy8F9$7j)eetYYr#-pYr2(gB;q4)*W#Ceb%imJW)MCKS^n7-r#U3~}#pJJDwl^`^)jKnH_3^IB#G^XHn2R}iC2{#x_O(Rf%F`{b{1RrH<-Tx>jR{4(4p#4YgQaGhopW<`TeCzv0_lAFUx-{Xyv0zuM);df`K<>Bn^ygS%||AJvR3j*PB>=0BRrWcZgo}2{)Qu4+k)P}#v$0hSzpVdtNS?vTekG${+a<j2|wNKqeyoFrnz0%2ep*lEo3O#fIDBpdz3Ltk@{Bwl8ptVK5G&Nb4I_c(sC*n5fetrXN}G&Us)+)sjso72R5CRg!I&lF^{&knPYmTd^j_x$$190ta=v@_8w8Q2g&~|MRm&`(ac&h"
_ORDER = ("Act 1", "Act 2", "Act 3", "Act 4", "Act 5", "Infinite", "Mastery")
_ROW_HEIGHT, _WIDTH = 22, 37


class ActLabelLocator:
    def __init__(self, min_score=0.78):
        pixels = zlib.decompress(base64.b85decode(_ATLAS))
        self.gray = np.frombuffer(pixels, dtype=np.uint8).reshape(7 * _ROW_HEIGHT, _WIDTH)
        self.min_score = min_score

    def __call__(self, frame, act):
        if act not in _ORDER:
            raise ValueError("Unknown Story act")
        if frame.ndim == 3 and frame.shape[2] == 4:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        elif frame.ndim == 3 and frame.shape[2] == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif frame.ndim == 2:
            gray = frame
        else:
            raise ValueError("Expected Roblox client capture")
        idx = _ORDER.index(act)
        target = self.gray[_ROW_HEIGHT * idx:_ROW_HEIGHT * (idx + 1)]
        best = None
        for scale in (0.70, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.55, 1.7):
            tw, th = round(_WIDTH * scale), round(_ROW_HEIGHT * scale)
            if tw >= gray.shape[1] or th >= gray.shape[0]:
                continue
            method = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
            template = cv2.resize(target, (tw, th), interpolation=method)
            scores = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(scores)
            if best is None or score > best[0]:
                best = (float(score), loc, tw, th)
        if best is None or best[0] < self.min_score:
            return None
        score, (left, top), tw, th = best
        return left + tw // 2, top + th // 2, score
