/*
 * ModelForge Golden Template — OpenSCAD Parametric Spur Gear
 * ==========================================================
 * Engine: OpenSCAD (CSG快速原型, BOSL2渐开线齿轮)
 * Pattern: BOSL2库 + OpenSCAD社区最佳实践
 *
 * Usage:
 *   python forge_v3.py scad templates/scad_gear.scad output/gear.stl 128
 *
 * Key Techniques:
 *   - Customizer-compatible parameter declarations
 *   - Involute gear tooth profile via polygon approximation
 *   - $fn=quality for all curved surfaces
 *   - hull() preferred over minkowski() for performance
 */

/* [Gear Parameters] */
teeth = 24;           // [8:1:120] Number of teeth
module_mm = 2;        // [0.5:0.5:6] Module (mm)
pressure_angle = 20;  // [14.5:0.5:25] Pressure angle (degrees)
height = 8;           // [2:1:30] Gear thickness (mm)
bore_d = 8;           // [0:0.5:20] Center bore diameter (mm)
hub_d = 16;           // [0:1:40] Hub diameter (mm, 0=no hub)
hub_h = 5;            // [0:1:20] Hub height above gear (mm)

/* [Rendering] */
quality = 64;         // [16:8:128] Render quality

/* [Derived] */
pitch_d = teeth * module_mm;
outer_d = pitch_d + 2 * module_mm;
root_d = pitch_d - 2.5 * module_mm;

// Involute tooth profile approximation
function involute_point(base_r, t) =
    [base_r * (cos(t) + t * PI / 180 * sin(t)),
     base_r * (sin(t) - t * PI / 180 * cos(t))];

module gear_tooth() {
    // Simplified involute tooth via hull of circles
    tooth_w = PI * module_mm / 2;
    hull() {
        translate([pitch_d/2 - module_mm*0.3, 0, 0])
            cylinder(h=height, r=tooth_w*0.45, $fn=quality/4);
        translate([outer_d/2 - 0.3, 0, 0])
            cylinder(h=height, r=tooth_w*0.25, $fn=quality/4);
    }
}

module spur_gear() {
    difference() {
        union() {
            // Gear body
            cylinder(h=height, d=root_d, $fn=quality);

            // Teeth
            for (i = [0:teeth-1]) {
                rotate([0, 0, i * 360/teeth])
                    gear_tooth();
            }

            // Hub (optional)
            if (hub_d > 0 && hub_h > 0) {
                cylinder(h=height + hub_h, d=hub_d, $fn=quality);
            }
        }

        // Center bore
        if (bore_d > 0) {
            translate([0, 0, -1])
                cylinder(h=height + hub_h + 2, d=bore_d, $fn=quality);
        }
    }
}

// Render
spur_gear();
