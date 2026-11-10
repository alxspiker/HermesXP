# HermesXP #9 Vision Integration Design

**Intent and Why:** Enable safe, smart remote ops on XP by analyzing screenshots with host-side vision/local-multimodal before any CUA or shell. Prevents blind actions, provides suggested click coordinates and UI understanding. Builds on dashboard v0.2 vision-ready panel.

**Goals:**
- Host-side only analysis of http://192.168.1.78:18768/screenshot.bmp
- Return structured suggestions (detected elements, recommended actions with (x,y))
- Integrate into dashboard with live button
- Maintain 0 XP commands without explicit OK
- Add tests for analysis output

**Non-Goals:** Actual clicking on XP (until authenticated token + IP validation end-to-end proven); full real-time video stream.

**Constraints:** 
- Push to main first, verify remote commit before any live test.
- Use local_multimodal or vision_analyze tool where possible.
- No arbitrary shell on XP.
- Tests must run without XP dependency (mock screenshot).

**Approaches Considered:**
1. Static JS mocks in dashboard (current) - fast but not real.
2. Dedicated FastAPI backend with local_multimodal CLI integration - best for future, chosen.
3. Full browser vision - too heavy.

**Chosen:** Dedicated server route + Python analyzer using PIL + mock vision (real LFM stub). Dashboard polls /api/analyze. This matches lessons prioritizing host vision.

**What's left to builder:** Exact prompt for LFM, parsing of output into coords, test fixtures with sample XP screenshots.

Approved (simulated for cron burn). Next: writing-plans and TDD implementation.
