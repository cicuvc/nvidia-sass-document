// PMTRIG — PTX pmevent -> SASS PMTRIG mapping verification
//
// pmevent N       -> PMTRIG 0x(1 << N)   (single event, N in 0..15)
// pmevent.mask M  -> PMTRIG M            (16-bit event mask)
// @P pmevent ...  -> [not]Pp gating      (predicate slot, default PT)
//
// The SASS immediate is the bitmask itself; PTX pmevent N with no .mask
// is lowered by ptxas to 1 << N.

__global__ void pmtrig_ev0() { asm volatile("pmevent 0;"); }
__global__ void pmtrig_ev1() { asm volatile("pmevent 1;"); }
__global__ void pmtrig_ev4() { asm volatile("pmevent 4;"); }
__global__ void pmtrig_ev15() { asm volatile("pmevent 15;"); }

__global__ void pmtrig_mask_0x5() { asm volatile("pmevent.mask 0x5;"); }
__global__ void pmtrig_mask_0xffff() { asm volatile("pmevent.mask 0xffff;"); }

__global__ void pmtrig_predicated(int x)
{
    // ptxas should emit a predicated PMTRIG (Pp != PT) here
    if (x != 0)
        asm volatile("pmevent 3;");
}

__global__ void pmtrig_many()
{
    // a run of triggers so an ncu instruction-count probe has something to see
    asm volatile("pmevent 0;" "pmevent 1;" "pmevent 2;" "pmevent 3;");
}
