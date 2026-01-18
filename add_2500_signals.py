# generate_tls.py
import string

# Output file
with open("grid_tls_logic.xml", "w") as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n<additional>\n\n')

    # Columns AA → BX (50 columns: A..B + A..X)
    # AA..AZ, BA..BZ, ... etc. We'll generate two-letter IDs.
    letters1 = ['A', 'B']  # First letter
    letters2 = list(string.ascii_uppercase[:50])  # Second letter: A-Z + extra logic below

    # For simplicity, we do AA..AX, BA..BX = 50x50 grid
    rows = range(50)  # 0..49

    for l1 in letters1:
        for l2_index, l2 in enumerate(string.ascii_uppercase):
            if l1 == 'B' and l2_index > 23:  # BX is last
                break
            for row in rows:
                junction_id = f"{l1}{l2}{row}"

                # Corner signals: first row, last row, first col, last col
                if ((row == 0 or row == 49) and ((l1 == 'A' and l2 == 'A') or (l1 == 'B' and l2 == 'X'))):
                    # single 90s phase for corner
                    f.write(f'    <tlLogic id="{junction_id}" type="static" programID="0" offset="0">\n')
                    f.write(f'        <phase duration="90" state="GG"/>\n')
                    f.write(f'    </tlLogic>\n\n')
                elif (l1 == 'A' and l2 == 'A'):
                    f.write(f'    <tlLogic id="{junction_id}" type="static" programID="0" offset="0">\n')
                    f.write(f'        <phase duration="42" state="GggrrrGGg"/>\n')
                    f.write(f'        <phase duration="3"  state="yyyrrrGyy"/>\n')
                    f.write(f'        <phase duration="42" state="rrrGGgGrr"/>\n')
                    f.write(f'        <phase duration="3"  state="rrryyyGrr"/>\n')
                    f.write(f'    </tlLogic>\n\n')
                elif (l1 == 'B' and l2 == 'X'):
                    f.write(f'    <tlLogic id="{junction_id}" type="static" programID="0" offset="0">\n')
                    f.write(f'        <phase duration="42" state="GGgGggrrr"/>\n')
                    f.write(f'        <phase duration="3"  state="Gyyyyyrrr"/>\n')
                    f.write(f'        <phase duration="42" state="GrrrrrGGg"/>\n')
                    f.write(f'        <phase duration="3"  state="Grrrrryyy"/>\n')
                    f.write(f'    </tlLogic>\n\n')
                elif (row == 0):
                    f.write(f'    <tlLogic id="{junction_id}" type="static" programID="0" offset="0">\n')
                    f.write(f'        <phase duration="42" state="rrrGGgGgg"/>\n')
                    f.write(f'        <phase duration="3"  state="rrrGyyyyy"/>\n')
                    f.write(f'        <phase duration="42" state="GGgGrrrrr"/>\n')
                    f.write(f'        <phase duration="3"  state="yyyGrrrrr"/>\n')
                    f.write(f'    </tlLogic>\n\n')
                elif (row == 49):
                    f.write(f'    <tlLogic id="{junction_id}" type="static" programID="0" offset="0">\n')
                    f.write(f'        <phase duration="42" state="GggrrrGGg"/>\n')
                    f.write(f'        <phase duration="3"  state="yyyrrrGyy"/>\n')
                    f.write(f'        <phase duration="42" state="rrrGGgGrr"/>\n')
                    f.write(f'        <phase duration="3"  state="rrryyyGrr"/>\n')
                    f.write(f'    </tlLogic>\n\n')
                else:
                    # Regular 4-phase template
                    f.write(f'    <tlLogic id="{junction_id}" type="static" programID="0" offset="0">\n')
                    f.write(f'        <phase duration="42" state="GGggrrrrGGggrrrr"/>\n')
                    f.write(f'        <phase duration="3"  state="yyyyrrrryyyyrrrr"/>\n')
                    f.write(f'        <phase duration="42" state="rrrrGGggrrrrGGgg"/>\n')
                    f.write(f'        <phase duration="3"  state="rrrryyyyrrrryyyy"/>\n')
                    f.write(f'    </tlLogic>\n\n')

    f.write('</additional>\n')

print("Done! grid_tls_logic.xml generated with 2500 junctions.")