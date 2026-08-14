#!/usr/bin/env python3
"""Generate sh/sysl/box2d/c/layout.sysl from the struct declarations beside it.

Box2D passes thirty-one different structs by value. A field declared one slot out of place links
perfectly and reads whatever is beside what it meant to read, which is a run-time failure in the
middle of a simulation wearing the clothes of a physics bug -- so every one of those layouts is
checked against Box2D's own headers by the C compiler, at build time, on the target being built for.

This reads the `struct` declarations out of `math.sysl` and `c.sysl` and emits, per type, a `c const`
holding `sizeof` and one holding `offsetof` per field, and an `@assert` comparing each against what
sysl laid out. Run it from the repository root after adding or reordering any field:

    python3 tools/genlayout.py

The sysl field name is mapped to C's by snake_case -> camelCase; EXCEPT below holds the one place
that is wrong, since `type` is a sysl keyword and the field is spelled `kind`.
"""
import re, sys

SRCS = ["sh/sysl/box2d/math/math.sysl", "sh/sysl/box2d/c/c.sysl"]
OUT = "sh/sysl/box2d/c/layout.sysl"

# sysl field name -> C field name, where the mechanical snake->camel is wrong
EXCEPT = {("BodyDef", "kind"): "type"}

def camel(s):
    parts = s.split("_")
    return parts[0] + "".join(p[0].upper() + p[1:] for p in parts[1:])

structs = []
cur = None
for line in [l for f in SRCS for l in open(f)]:
    m = re.match(r"^struct (\w+)$", line.rstrip())
    if m:
        cur = (m.group(1), [])
        structs.append(cur)
        continue
    m = re.match(r"^    (\w+): ", line)
    if m and cur is not None:
        cur[1].append(m.group(1))
        continue
    if line.strip() and not line.startswith("    "):
        cur = None

out = []
out.append("""// Every one of these types is checked against Box2D's own header, by the C compiler, on the target
// being built for.
//
// **A binding to a library that passes structs by value is a promise about layout, and nothing
// ordinarily checks it.** A field declared one slot out of place links perfectly, compiles without a
// warning, and reads whatever happens to be next to what it meant to read. The failure lands at run
// time, in the middle of a simulation, looking like a physics bug.
//
// So this file asks. `c const` measures a `sizeof` and an `offsetof` per field out of `box2d/`'s
// real headers, `@assert` compares each against what sysl laid out for the type beside it, and a
// disagreement is a **compile error naming the field and both numbers**:
//
//     error: assertion failed: b2Version.minor is not where box2d puts it
//            — the left side is 8 and the right side is 4
//
// It costs nothing at run time: both sides are constants, and `@assert` is a compile-time claim.
//
// **It is also per target.** A cross build to a machine whose `bool` or pointer is a different width
// re-measures rather than trusting what was true on the machine the binding was written on.
//
// This file is generated from the declarations in `c.sysl` and should be regenerated rather than
// edited — but read it, because what it says is the whole argument that the binding beside it is
// correct.
""")
out.append("""module sh.sysl.box2d.c

// **These two lines are not a duplicate of `c.sysl`'s.** A `c const` block is measured in a probe
// translation unit of its own, and that unit includes what the *file* the block came from names — so
// without them this file's three hundred measurements would be about nothing. The attribute has to
// sit here, directly under `module` and above the import, which is where the compiler asks for it.
@include("stddef.h")
@include("box2d/box2d.h")

import sh.sysl.box2d.math.{Vec2, CosSin, Rot, Transform, Mat22, AABB, Plane}
""")

for name, fields in structs:
    ctype = "b2" + name
    out.append(f"// `{ctype}` — {len(fields)} fields")
    out.append("c const")
    out.append(f'    SIZEOF_{name.upper()}: usize = "sizeof({ctype})"')
    for f in fields:
        cf = EXCEPT.get((name, f), camel(f))
        out.append(f'    OFF_{name.upper()}_{f.upper()}: usize = "offsetof({ctype}, {cf})"')
    out.append("")
    out.append(f'@assert(sizeof({name}) == SIZEOF_{name.upper()}, "{ctype} is not the size box2d says it is")')
    for f in fields:
        out.append(f'@assert(offsetof({name}, {f}) == OFF_{name.upper()}_{f.upper()}, '
                   f'"{ctype}.{EXCEPT.get((name, f), camel(f))} is not where box2d puts it")')
    out.append("")

open(OUT, "w").write("\n".join(out))
print(f"{len(structs)} structs, {sum(len(f) for _, f in structs)} fields")
