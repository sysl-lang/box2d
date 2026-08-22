# box2d

2D rigid body physics for [sysl](https://sysl.sh) — bodies, shapes, joints, contacts and queries,
from [Box2D](https://github.com/erincatto/box2d) v3.1.1.

```sysl
import sh.sysl.box2d.{world, body_def, shape_def, circle, make_box, BodyKind}
import sh.sysl.box2d.math.{Vec2, zero}

val w = world(gravity = Vec2(0.0, -10.0))

val ground = w.body(body_def(position = Vec2(0.0, -1.0)))

ground.polygon(shape_def(), make_box(50.0, 1.0))

val ball = w.body(body_def(kind = BodyKind.Dynamic, position = Vec2(0.0, 6.0)))

ball.circle(shape_def(density = 1.0, friction = 0.3), circle(zero(), 0.5))

for _ in 0..<180
    w.step(1.0 / 60.0)

print(ball.position())        -- (0.0, 0.5), resting on the ground
```

## Using it

```hocon
dependencies {
  box2d { git = "github.com/sysl-lang/box2d", version = "0.1.1" }
}
```

**Nothing has to be installed.** Box2D is not in Homebrew and there is no system copy to link on a
microcontroller, so its thirty-five translation units are carried in this package and compiled with
it. There is no include path to pass and no `requires { headers }` to answer.

## What is here

| module | what it is |
|---|---|
| `sh.sysl.box2d` | the API — `World`, `Body`, `Shape`, `Chain`, the eight joints, queries, events |
| `sh.sysl.box2d.math` | `Vec2`, `Rot`, `Transform`, `AABB`, with operators. Pure sysl, usable alone |
| `sh.sysl.box2d.c` | Box2D declared verbatim, and Box2D's own C. **An application should not need it** |

### The structs an application names are named from the top module

Box2D's shapes, ids, defs and events are declared in `c`, because `c`'s own signatures take them and
a module may not depend on a module that depends on it. They are named from `sh.sysl.box2d` anyway,
as transparent aliases in `types.sysl`:

```sysl
type Polygon = c.Polygon
type ShapeId = c.ShapeId
type ContactHitEvent = c.ContactHitEvent
```

An alias declares no type. A value built through either name is the same value, crosses to C in the
same registers, and satisfies both names — so this costs nothing at run time, and the package's tests
check it by handing a value built above to a declaration written below. What is aliased is what a
*public signature of the top module names*: everything else stays in `c`, because nothing above ever
hands one to a caller.

This is what needs sysl **0.0.67**, the release a transparent alias over a struct arrived in, and
`package.hocon` states that floor.

**Build a shape with `circle`, `capsule`, `segment` or `make_box` rather than by naming the struct.**
Five of the aliased names — `Circle`, `Capsule`, `Segment`, `Polygon`, `Filter` — are also variants
of `ShapeKind` or `JointKind`, and in call position the variant wins, so `Circle(zero(), 0.5)` is
read as the variant and refused for taking arguments. In type position, which is what the names are
for, there is no contest. The lowercase builders in `defs.sysl` are the pleasant spelling anyway.

## Three things worth knowing before reading the source

### Every struct's layout is checked by the C compiler, at build time

Box2D passes **thirty-one different structs by value**, and a binding to a library like that is a
promise about layout that nothing ordinarily checks. A field declared one slot out of place links
perfectly, compiles without a warning, and reads whatever is beside what it meant to read — a
failure at run time, in the middle of a simulation, wearing the clothes of a physics bug.

`sh/sysl/box2d/c/layout.sysl` asks instead. It measures a `sizeof` and an `offsetof` per field out
of Box2D's real headers with `c const`, and `@assert`s each against what sysl laid out — **305
fields**, at compile time, on the target being built for, at no run-time cost. A disagreement names
the field and both numbers:

```
error: assertion failed: b2Version.minor is not where box2d puts it
       — the left side is 8 and the right side is 4
```

That is `design/15 §7`'s complaint about a transcribed constant — *"correct on one machine, and
nothing checks it"* — answered for a layout rather than for a number.

The file is generated. After adding or reordering any field, run `python3 tools/genlayout.py` from
the repository root rather than editing it.

### Nothing is destroyed by hand, and only the world has a destructor

There is no `destroy` in this API. A `World` is `&World` with an `impl Drop`.

A body, a shape and a joint have **no destructor**, and that is a decision rather than an omission:
`b2DestroyWorld` frees every one of them, so a second destructor would be freeing storage that had
already gone. What replaces it is a field — `Body`, `Shape`, `Chain` and `Joint` each hold a
`&World`, so the world outlives everything made in it and the ordering Box2D requires cannot be
written wrongly.

`remove()` still takes one out early, which is what a game object dying needs. Every id carries a
generation counter, so anything holding a removed body afterwards finds `is_valid()` false rather
than crashing.

### There is no `opaque struct` here, and no shim

Every other binding in this org hides its handles behind `opaque struct`, because a handle is a
pointer. A Box2D id is not: it is an index and a generation, passed by value. Declaring it opaque
would be a lie about what it is, and would also stop it crossing to C at all, since `15 §9`
withholds exactly the size a by-value parameter needs.

And there is **no C of this binding's own**. Every Box2D entry point takes scalars, pointers or
structs by value, all of which sysl can spell, so the `.c` files in `c/` are Box2D's and unedited.

## Callbacks are sysl functions

Box2D's solver is multithreaded and does not call back into an application while it is stepping:
contacts, sensor overlaps and body movement are buffered and read after the step as arrays. So
almost nothing here takes a function.

Where Box2D genuinely does want one — a query's visitor, custom filtering, pre-solve, and the
friction and restitution mixers — it takes a sysl function directly. **No C trampoline is needed and
none is written.**

```sysl
@export
refuse_everything(a: ShapeId, b: ShapeId, ctx: *u8) -> bool = false

w.set_custom_filter(&refuse_everything, null)
```

This is new. Those signatures take a `b2ShapeId` and a `b2Vec2` **by value**, and before sysl
**0.0.55** an aggregate parameter meant a sysl function had no address C could call — the survey for
this package planned thirteen C trampolines to work around it. `@export` is what earns the address,
and the compiler says so if it is left off.

## The math is written in sysl, not shimmed

Box2D's public surface is 466 entry points and **seventy-nine `static inline` math functions**. The
inline ones have no symbol, so a binding cannot link them, and `15 §7` would have them shimmed.
`sh.sysl.box2d.math` writes them in sysl instead — every one is two or three lines of arithmetic
over two floats, so seventy-nine C wrappers would exist only to be crossed, and what a caller would
get for them is `b2Add(a, b)` where `a + b` was meant.

`cos_sin` and `atan2` are Box2D's own polynomial approximations rather than libm's, because that is
why Box2D has them: a simulation replays identically on two machines with two different libms. Two
tests compare this module's answers with the library's own, **bit for bit**, over 73 angles and 289
quadrant pairs. They agree exactly, which is what makes it a port rather than a rewrite.

The consequence is that `sh.sysl.box2d.math` is usable with no physics engine at all: a small 2D
linear algebra library in pure sysl that happens to have Box2D's exact layouts.

## Tests

```
sysl test .
```

**52 tests, 0 failures.** Most of them run a simulation and read a number back, because a binding
can be wrong in a way that compiles, links and returns without complaint. Two of them measure the
callback path against the shipped compiler through a real Box2D registration rather than a probe.

Two real defects were found while the tests were being written, and both are worth repeating
because neither would have been visible any other way:

- `world()` had `maximum_linear_speed = 4.0` and Box2D's default is **400** — a transcribed number
  that was simply wrong. The fix was better than the correction: the three speed thresholds all
  scale with `b2_lengthUnitsPerMeter`, so no default written here can be right at more than one
  length unit. They are no longer parameters at all.
- The rotation-composition test's tolerance is 0.005 and not 0.001, because the measured error is
  0.0026. That is the honest cost of the approximations, and it is written down rather than tuned
  until it passed.

## What is not bound

The debug-draw interface (`b2DebugDraw`, eleven function-pointer slots), the low-level distance and
time-of-impact functions, the dynamic tree, the character mover, and Box2D's task-system hooks.
`worker_count` is deliberately left at one: a count above it is a promise to supply a task system,
and a package that let it be set without one would be handing Box2D a promise nobody keeps.

## Licence

ISC for the binding, MIT for Box2D. See `LICENSE`.
