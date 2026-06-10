# Asset-Grounded Tutorial / Demo Scene Catalog

Creative-but-grounded scene ideas for Isaac Assist tutorials. Every asset named below is **verified on disk** at:

```
ROOT = /mnt/shared_data/isaac-sim-assets-complete-5.0.0/Assets/Isaac/5.0/Isaac/
```

Key verified paths (used throughout):
- Robots: `Robots/FrankaRobotics/...`, `Robots/UniversalRobots/{ur3,ur5,ur10,ur16e,ur20,ur30,...}/ur10.usd` + `ur10/grippers/{short,long}_gripper.usd`, `Robots/Fanuc/CRX10IAL`, `Robots/Kuka`, `Robots/Kinova/Gen3`, `Robots/Techman`, `Robots/Ufactory`, `Robots/Robotiq/{2F-85,2F-140,Hand-E}`, `Robots/BostonDynamics/spot`, `Robots/ANYbotics`, `Robots/Unitree/{G1,H1,Go1,Go2}`, `Robots/NVIDIA/{NovaCarter/nova_carter.usd,Carter,Jetbot,Kaya}`
- Props: `Props/Conveyors/ConveyorBelt_A01.usd … A49.usd`, `Props/KLT_Bin/small_KLT.usd`, `Props/Pallet/{pallet.usd,pallet_holder.usd,o3dyn_pallet.usd}`, `Props/PackingTable/packing_table.usd`, `Props/Factory/factory_bolt_m{4,8,12,16,20}_{loose,tight}`, `Props/Blocks/{nvidia_cube.usd,DexCube,basic_block.usd,red/green/blue/yellow_block.usd}`, `Props/YCB/Axis_Aligned/*` (002_master_chef_can … 061_foam_brick), `Props/Mugs/SM_Mug_{A2,B1,C1,D1}.usd`, `Props/Food/mac_n_cheese.usd`, `Props/Beaker/beaker_500ml.usd`, `Props/Rubiks_Cube`, `Props/Sektion_Cabinet/sektion_cabinet_instanceable.usd`, `Props/Forklift/forklift.usd`, `Props/Mounts/{ur10_mount.usd,table.usd,thor_table.usd}`
- Environments: `Environments/Simple_Warehouse/{full_warehouse.usd,warehouse.usd,warehouse_with_forklifts.usd,warehouse_multiple_shelves.usd}`, `Environments/Digital_Twin_Warehouse`, `Environments/Modular_Warehouse`, `Environments/Hospital/hospital.usd`, `Environments/Office`, `Environments/Simple_Room`

**Complexity ladder:** T1 (one robot, one object, one table) → T7 (full warehouse, multiple stations + AMR). Each tier reuses assets/skills from the prior so the catalog reads as a curriculum, not a grab-bag.

---

## T1 — Atomic single-robot, single-object

### T1.1 — "Touch the Cube"
- **Scene:** A Franka on a table reaches and rests its end-effector on a single cube.
- **Assets:** `FrankaRobotics/franka.usd` + `Mounts/table.usd` + `Blocks/nvidia_cube.usd`
- **Persona:** A *machine-tending technician* wants to confirm the robot can reach a target point before trusting it with parts.
- **Teaches:** Inverse-kinematics reach to a static world coordinate (no grasp). The "hello world" of the whole ladder.

### T1.2 — "First Pick"
- **Scene:** UR5 on its mount picks up a single red block and lifts it 20 cm.
- **Assets:** `UniversalRobots/ur5/ur5.usd` + `Robotiq/2F-85` + `Mounts/table.usd` + `Blocks/red_block.usd`
- **Persona:** A *CNC loader* wants to grip-and-lift a billet off a fixture.
- **Teaches:** Parallel-jaw grasp + lift (open/close gripper timed to approach). First closed-loop grasp.

### T1.3 — "Place It Down"
- **Scene:** Cobotta/UR3 picks a DexCube and places it on a marked spot on the same table.
- **Assets:** `UniversalRobots/ur3/ur3.usd` + `Blocks/DexCube` + `Mounts/table.usd`
- **Persona:** A *kitting assembler* wants to relocate one part precisely.
- **Teaches:** Full pick→transit→place with a placement tolerance check. Adds the "place" half of pick-place.

### T1.4 — "Suction Sampler"
- **Scene:** UR10 with the long suction gripper lifts a flat foam brick by vacuum.
- **Assets:** `UniversalRobots/ur10/ur10.usd` + `ur10/grippers/long_gripper.usd` + `ur10_mount.usd` + `YCB/Axis_Aligned/061_foam_brick.usd`
- **Persona:** A *warehouse picker* wants to handle flat/boxy items a jaw can't grip well.
- **Teaches:** Suction/vacuum grasp on a flat top face — distinct gripper physics from the parallel jaw (compliance + surface contact).

---

## T2 — Single robot, multi-object / sorting / containers

### T2.1 — "Bin It"
- **Scene:** Franka picks three YCB cans off a table and drops each into a KLT bin.
- **Assets:** `FrankaRobotics/franka.usd` + `Props/KLT_Bin/small_KLT.usd` + `YCB/{005_tomato_soup_can,007_tuna_fish_can,010_potted_meat_can}.usd` + `table.usd`
- **Persona:** A *warehouse picker* wants to consolidate loose stock into a tote.
- **Teaches:** Multi-object iteration + dropping into a **container** (release-over-bin, not place-on-surface). Introduces the bin as a deposit target.

### T2.2 — "Color Sort"
- **Scene:** UR10 sorts red/green/blue blocks into three separate KLT bins by color.
- **Assets:** `ur10.usd` + `Robotiq/2F-140` + `Blocks/{red,green,blue,yellow}_block.usd` + 3× `KLT_Bin/small_KLT.usd`
- **Persona:** A *quality inspector / sorter* wants to route parts to lanes by an attribute.
- **Teaches:** Attribute-based routing — same grasp, **different destination chosen by object property**. First "decision" task.

### T2.3 — "Mug Tree"
- **Scene:** Techman/UR5 stacks/aligns four different mug models neatly on a packing table.
- **Assets:** `Techman/...` or `ur5.usd` + `Mugs/SM_Mug_{A2,B1,C1,D1}.usd` + `PackingTable/packing_table.usd`
- **Persona:** A *kitting assembler* wants to arrange mixed SKUs into a tidy presentation.
- **Teaches:** Handling **heterogeneous geometry** (4 mug shapes, 4 grasp poses) + an ordered layout pattern.

### T2.4 — "Stack of Three"
- **Scene:** Kinova Gen3 builds a 3-cube vertical stack.
- **Assets:** `Kinova/Gen3` + `Blocks/nvidia_cube.usd` (×3, color-tagged) + `table.usd`
- **Persona:** A *palletizer operator (trainee)* wants to learn vertical stacking before doing it with boxes.
- **Teaches:** **Stacking** — place onto a moving top surface (the growing stack), height bookkeeping, and not knocking the base. The classic precision test.

---

## T3 — Conveyor / flow / timing

### T3.1 — "Catch & Divert"
- **Scene:** Boxes ride a conveyor; a UR10 picks each as it arrives and sets it on a static table.
- **Assets:** `Props/Conveyors/ConveyorBelt_A01.usd` + `ur10.usd` + `ur10/grippers/short_gripper.usd` + `YCB/004_sugar_box.usd` (spawned repeatedly) + `table.usd`
- **Persona:** A *line operator* wants to pull defective/flagged items off a running line.
- **Teaches:** **Moving-target timing** — track belt speed, pick from a moving frame, idle until next part. First dynamic-environment task.

### T3.2 — "Conveyor-to-Bin Pick"
- **Scene:** Parts on a belt are picked into a KLT bin staged beside the line.
- **Assets:** `ConveyorBelt_A02.usd` + `ur5.usd` + `Robotiq/2F-85` + `KLT_Bin/small_KLT.usd` + `Blocks/basic_block.usd`
- **Persona:** A *warehouse picker* wants to tote up items flowing off a sorter.
- **Teaches:** Combines T2.1 (bin) + T3.1 (belt) — pick-from-flow **and** deposit-to-container in one loop.

### T3.3 — "Two-Belt Transfer"
- **Scene:** Robot lifts items from an infeed belt and drops them onto a parallel outfeed belt.
- **Assets:** `ConveyorBelt_A03.usd` + `ConveyorBelt_A04.usd` (parallel) + `Fanuc/CRX10IAL` + `YCB/009_gelatin_box.usd`
- **Persona:** A *line operator / line-balancer* wants to bridge two asynchronous lines.
- **Teaches:** Source **and** destination both moving — two independent belt frames, hand-off timing.

### T3.4 — "Lane Merge Sort"
- **Scene:** Mixed YCB boxes on one belt are sorted onto two outfeed belts by size.
- **Assets:** `ConveyorBelt_A05.usd` (infeed) + `A06.usd` + `A07.usd` (outfeed) + `ur16e/ur16e.usd` + `YCB/{003_cracker_box,008_pudding_box,009_gelatin_box}.usd`
- **Persona:** A *quality inspector* on a high-throughput line wants automated lane assignment.
- **Teaches:** T2.2 routing logic + T3.3 dual-belt motion fused → routing **on dynamic source and dynamic destinations**.

---

## T4 — Assembly / machine-tending / fixtures

### T4.1 — "Bolt the Plate"
- **Scene:** UR10 picks M12 bolts from a feeder tray and places them into bolt holes on a fixture.
- **Assets:** `ur10.usd` + `Robotiq/Hand-E` + `Factory/factory_bolt_m12_loose` (×6) + `factory_bolt_m12_tight` (as installed reference) + `table.usd`
- **Persona:** A *machine assembly tech* wants automated fastener insertion.
- **Teaches:** **High-precision insertion** into small holes (mm tolerance), grasping small cylindrical parts, loose→tight state representation. First true "assembly."

### T4.2 — "Mac-and-Cheese Kitting"
- **Scene:** Robot assembles a meal kit: a food box + a mug + a soup can placed into a KLT bin in a fixed layout.
- **Assets:** `ur5.usd` + `Robotiq/2F-85` + `Food/mac_n_cheese.usd` + `Mugs/SM_Mug_B1.usd` + `YCB/005_tomato_soup_can.usd` + `KLT_Bin/small_KLT.usd`
- **Persona:** A *kitting assembler* building mixed-SKU order bundles.
- **Teaches:** **Recipe/BOM-driven multi-item assembly** with per-item placement slots — a deterministic kit layout, not a heap.

### T4.3 — "Cabinet Tending"
- **Scene:** Robot opens a Sektion cabinet drawer, places an item inside, closes it.
- **Assets:** `Franka` + `Sektion_Cabinet/sektion_cabinet_instanceable.usd` + `Blocks/yellow_block.usd`
- **Persona:** A *machine-tending technician* loading a closed enclosure / parts cabinet.
- **Teaches:** **Articulated-fixture interaction** — operate a drawer/door joint (pull handle, swing/slide), then act inside the opened volume. First articulated-world manipulation.

### T4.4 — "Lab Sample Transfer"
- **Scene:** UR3e moves a 500 ml beaker between two thorlabs-style benches without spilling.
- **Assets:** `ur3e/ur3e.usd` + `Robotiq/2F-85` + `Beaker/beaker_500ml.usd` + 2× `Mounts/thor_table.usd`
- **Persona:** A *lab automation technician* wants hands-off sample handling.
- **Teaches:** **Orientation-constrained transport** (keep vessel upright through the whole path) — a motion constraint on top of pick-place.

---

## T5 — Multi-station cells (robot + conveyor + container + fixture)

### T5.1 — "Pick → Inspect → Pack Cell"
- **Scene:** A 3-station U-cell: UR10 picks from a belt, presents the part to a camera station, then packs good parts into a KLT bin on a packing table.
- **Assets:** `ConveyorBelt_A08.usd` + `ur10.usd` + `Props/Camera/...` + `PackingTable/packing_table.usd` + `KLT_Bin/small_KLT.usd` + `YCB/003_cracker_box.usd`
- **Persona:** A *quality inspector* running an inline inspect-and-pack station.
- **Teaches:** **Sequenced multi-station workflow** with a branch (pass→pack / fail→reject). Chains T3+T2+a decision gate.

### T5.2 — "Palletize the Cartons"
- **Scene:** UR20 (long reach) stacks cartons coming off a belt into a 2×2×2 layer pattern on a wooden pallet.
- **Assets:** `ur20/ur20.usd` + `ConveyorBelt_A09.usd` + `Pallet/pallet.usd` + `YCB/004_sugar_box.usd` (×8) + `ur10_mount.usd`
- **Persona:** A *palletizer operator* wants end-of-line case stacking.
- **Teaches:** **Layer-pattern palletizing** — 3D stacking with a programmatic pattern + reach envelope of a large UR. Scales T2.4 stacking to a real pallet grid.

### T5.3 — "Dual-Arm Handoff Cell"
- **Scene:** Two Frankas face each other across a belt; arm A picks from infeed and hands to arm B which packs into a bin.
- **Assets:** 2× `Franka` + `ConveyorBelt_A10.usd` + `KLT_Bin/small_KLT.usd` + `Blocks/DexCube`
- **Persona:** A *line operator* designing a space-constrained two-robot cell.
- **Teaches:** **Multi-robot coordination / handoff** — mid-air or over-fixture transfer, mutex on the shared workspace. First multi-arm sync.

### T5.4 — "CNC Load/Unload"
- **Scene:** Robot pulls a finished part out of a cabinet "machine," drops it on an outfeed belt, loads a fresh blank from a bin.
- **Assets:** `Fanuc/CRX10IAL` + `Sektion_Cabinet` (as machine enclosure) + `ConveyorBelt_A11.usd` + `KLT_Bin/small_KLT.usd` + `Blocks/nvidia_cube.usd`
- **Persona:** A *CNC machine-tending technician* automating load/unload cycles.
- **Teaches:** Cyclic **load-unload state machine** with an articulated machine door (T4.3) + belt (T3) + bin (T2) — the canonical machine-tending loop.

---

## T6 — Mobile manipulation + AMR logistics

### T6.1 — "AMR Tote Shuttle"
- **Scene:** Nova Carter AMR ferries a loaded KLT bin from a pick station to a drop zone across the floor.
- **Assets:** `NVIDIA/NovaCarter/nova_carter.usd` + `KLT_Bin/small_KLT.usd` + `Environments/Simple_Room` (or warehouse tile)
- **Persona:** A *warehouse AMR / intralogistics coordinator* wants autonomous tote movement.
- **Teaches:** **Mobile base navigation** with a payload — point-to-point drive, no arm yet. Introduces the AMR.

### T6.2 — "Quadruped Inspection Round"
- **Scene:** Spot walks a patrol route past racks, pausing at marked inspection points.
- **Assets:** `BostonDynamics/spot` + `Environments/Simple_Warehouse/warehouse.usd`
- **Persona:** A *facility / quality inspector* wanting autonomous walking inspection.
- **Teaches:** **Legged locomotion + waypoint patrol** over uneven/aisle terrain — a non-wheeled mobile platform.

### T6.3 — "Carter + Arm Mobile Pick"
- **Scene:** AMR drives to a shelf, and a mounted/co-located UR5 picks an item into the AMR's onboard bin, then drives to delivery.
- **Assets:** `NovaCarter/nova_carter.usd` + `ur5.usd` + `Robotiq/2F-85` + `KLT_Bin/small_KLT.usd` + `YCB/006_mustard_bottle.usd` + warehouse shelf tile
- **Persona:** A *autonomous order picker* (mobile manipulation).
- **Teaches:** **Mobile manipulation** = navigate (T6.1) + arm pick (T1/T2) in one coordinated mission. The first "drive-then-grasp."

### T6.4 — "Humanoid Household Assist"
- **Scene:** Unitree G1/H1 retrieves a mug from a Sektion cabinet and sets it on a counter.
- **Assets:** `Unitree/{G1,H1}` + `Sektion_Cabinet/sektion_cabinet_instanceable.usd` + `Mugs/SM_Mug_C1.usd` + `Simple_Room`
- **Persona:** A *home/service robotics developer* prototyping domestic assistance.
- **Teaches:** **Bipedal whole-body manipulation** — locomotion + reach + articulated cabinet (T4.3) on a humanoid. Surprising-but-grounded: real G1 + real cabinet assets.

---

## T7 — Full-warehouse, multi-station, multi-agent

### T7.1 — "Receiving Dock to Stock"
- **Scene:** Forklift-staged pallets at the dock; a UR20 depalletizes cartons onto a belt that feeds a put-away station, in the full warehouse.
- **Assets:** `Environments/Simple_Warehouse/warehouse_with_forklifts.usd` + `Forklift/forklift.usd` + `Pallet/pallet.usd` + `ur20/ur20.usd` + `ConveyorBelt_A12.usd` + `YCB/003_cracker_box.usd` (pile)
- **Persona:** A *inbound logistics / forklift operator* automating goods-in.
- **Teaches:** **Depalletizing** (inverse of T5.2) inside a real environment with forklift traffic + belt handoff. First end-to-end inbound flow.

### T7.2 — "Goods-to-Person Picking Station"
- **Scene:** Nova Carter AMRs shuttle KLT totes from shelves to a stationary UR10 pick-and-pack station in `full_warehouse`.
- **Assets:** `Environments/Simple_Warehouse/full_warehouse.usd` + 2× `NovaCarter/nova_carter.usd` + `ur10.usd` + 3× `KLT_Bin/small_KLT.usd` + `PackingTable/packing_table.usd` + assorted YCB
- **Persona:** A *fulfillment / e-commerce order-pick coordinator*.
- **Teaches:** **Fleet ↔ fixed-robot orchestration** — AMRs queue at a station, station empties/refills totes, throughput scheduling. Multi-agent traffic + a manipulation station.

### T7.3 — "End-to-End Order Line"
- **Scene:** Full pipeline in `full_warehouse`: depalletize (UR20) → belt → sort (Fanuc) → kit-pack (Franka) → AMR (Carter) delivers the finished order to a shipping pallet.
- **Assets:** `full_warehouse.usd` + `ur20.usd` + `Fanuc/CRX10IAL` + `Franka` + `NovaCarter/nova_carter.usd` + `ConveyorBelt_A13/A14.usd` + `Pallet/pallet.usd` + `KLT_Bin/small_KLT.usd` + YCB mix
- **Persona:** A *warehouse operations manager / systems integrator* validating a whole automated line.
- **Teaches:** **Full multi-station, multi-robot pipeline** — the capstone. Every prior tier appears as a sub-stage (depal T7.1, sort T3.4, kit T4.2, palletize T5.2, AMR delivery T6.3).

### T7.4 — "Mixed-Fleet Floor"
- **Scene:** Carter AMRs do tote logistics, Spot patrols for inspection, and two arm cells work in parallel — heterogeneous fleet sharing one warehouse floor.
- **Assets:** `full_warehouse.usd` + 2× `NovaCarter` + `BostonDynamics/spot` + `ur10.usd` + `Franka` + conveyors + pallets + bins
- **Persona:** A *smart-factory / fleet orchestration architect*.
- **Teaches:** **Heterogeneous multi-robot floor** (wheeled + legged + fixed arms) with shared-space avoidance + role separation (logistics vs inspection vs manipulation). The "digital-twin floor" demo.

---

## Cross-cutting "surprising-but-grounded" extras

### X1 — "Rubik's Dexterity Probe"
- **Scene:** Dual Franka / a single arm with re-grasp manipulates a Rubik's cube between fixed orientations.
- **Assets:** `Franka` + `Props/Rubiks_Cube` + `table.usd`
- **Persona:** A *dexterous-manipulation researcher*.
- **Teaches:** **In-hand / re-grasp reorientation** — a pure manipulation-skill benchmark separate from the logistics ladder.

### X2 — "Hospital Supply Run"
- **Scene:** Nova Carter delivers a tote of supplies through hospital corridors to a room marker.
- **Assets:** `Environments/Hospital/hospital.usd` + `NovaCarter/nova_carter.usd` + `KLT_Bin/small_KLT.usd`
- **Persona:** A *hospital logistics technician*.
- **Teaches:** Navigation in a **non-warehouse semantic environment** (corridors, doorways) — generalizes T6.1 away from the factory.

### X3 — "Office Fetch"
- **Scene:** Unitree Go2 / G1 fetches an item across an office and returns it.
- **Assets:** `Environments/Office/...` + `Unitree/Go2` (or `G1`) + `YCB/025_mug` or `Mugs/SM_Mug_A2.usd`
- **Persona:** A *service-robotics developer*.
- **Teaches:** Mobile fetch in a cluttered human environment — bridges T6 mobility to everyday spaces.

### X4 — "Pallet-Holder Staging"
- **Scene:** Robot loads empty KLT bins into a pallet holder for outbound staging.
- **Assets:** `ur10.usd` + `Pallet/pallet_holder.usd` + 4× `KLT_Bin/small_KLT.usd`
- **Persona:** A *outbound staging / dispatch operator*.
- **Teaches:** **Rack/holder slotting** — placing into discrete indexed slots of a holder fixture (a structured variant of palletizing).

---

## How to read this as a curriculum

| Tier | Adds (vs prior) | Smallest asset set |
|------|-----------------|--------------------|
| T1 | IK reach, single grasp, suction | robot + table + 1 object |
| T2 | multi-object, containers, routing, stacking | + KLT bins + colored blocks |
| T3 | dynamic timing on conveyors | + ConveyorBelt_A0x |
| T4 | assembly, insertion, articulated fixtures, constraints | + Factory bolts / Sektion cabinet / Beaker |
| T5 | sequenced multi-station + multi-arm cells | + PackingTable + Pallet + 2nd robot |
| T6 | mobile bases, legged, humanoid, mobile manipulation | + NovaCarter / Spot / Unitree |
| T7 | full environment, fleets, end-to-end pipelines | + full_warehouse + Forklift + fleet |

Each tier strictly **reuses** assets and skills from the one below it, so a single asset library grows a 7-rung skill ladder across ~9 personas (warehouse picker, palletizer, machine-tending tech, CNC loader, kitting assembler, quality inspector, AMR/forklift logistics, lab automation tech, hospital/service logistics) plus dexterity-research and humanoid-assist tracks.
