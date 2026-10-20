package com.joescrepes.courtside.ui.lineup

import com.joescrepes.courtside.data.LineupIntent
import com.joescrepes.courtside.data.Player
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LineupLogicTest {
    private fun p(id: Int, slot: String, vararg eligible: String, injury: String = "ACTIVE", locked: Boolean = false) =
        Player(id = id, name = "P$id", slot = slot, eligibleSlots = eligible.toList() + listOf("UTIL", "BE", "IR"),
               injuryStatus = injury, lineupLocked = locked)

    private val counts = mapOf("PG" to 1, "C" to 1, "UTIL" to 2, "BE" to 2, "IR" to 1)
    private val pg = p(1, "PG", "PG")
    private val center = p(2, "C", "C")
    private val util = p(3, "UTIL", "PG", "C")
    private val benchGuard = p(4, "BE", "PG")
    private val hurt = p(5, "BE", "C", injury = "OUT")
    private val roster = listOf(pg, center, util, benchGuard, hurt)

    @Test fun `seats include empty slots in ESPN order`() {
        val s = seats(roster, counts)
        assertEquals(listOf("PG", "C", "UTIL", "UTIL", "BE", "BE", "IR"), s.map { it.slot })
        assertNull(s[3].player)  // second UTIL is open
        assertNull(s[6].player)  // IR is open
    }

    @Test fun `bench player onto full starter slot swaps with the occupant`() {
        assertEquals(LineupIntent("4", "PG", swapWith = "1"), intentFor(benchGuard, Seat("PG", pg), roster, counts))
    }

    @Test fun `move into an open seat needs no swap`() {
        assertEquals(LineupIntent("4", "UTIL"), intentFor(benchGuard, Seat("UTIL", null), roster, counts))
    }

    @Test fun `starter tapped onto a bench player brings that player in`() {
        assertEquals(LineupIntent("4", "PG", swapWith = "1"), intentFor(pg, Seat("BE", benchGuard), roster, counts))
    }

    @Test fun `starter to an empty bench seat just sits`() {
        val oneOnBench = roster - hurt
        assertEquals(LineupIntent("1", "BE"), intentFor(pg, Seat("BE", null), oneOnBench, counts))
    }

    @Test fun `ineligible, locked, same-slot and healthy-IR moves are refused`() {
        assertNull(intentFor(center, Seat("PG", pg), roster, counts))
        assertNull(intentFor(benchGuard, Seat("PG", pg.copy(lineupLocked = true)), roster, counts))
        assertNull(intentFor(benchGuard.copy(lineupLocked = true), Seat("UTIL", null), roster, counts))
        assertNull(intentFor(benchGuard, Seat("BE", hurt), roster, counts))
        assertNull(intentFor(benchGuard, Seat("IR", null), roster, counts))
        assertEquals(LineupIntent("5", "IR"), intentFor(hurt, Seat("IR", null), roster, counts))
    }
}
