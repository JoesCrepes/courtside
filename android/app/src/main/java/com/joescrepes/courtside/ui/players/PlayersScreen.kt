package com.joescrepes.courtside.ui.players

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.joescrepes.courtside.data.Player
import com.joescrepes.courtside.ui.ConfirmSheet
import com.joescrepes.courtside.ui.ErrorPane
import com.joescrepes.courtside.ui.Headshot
import com.joescrepes.courtside.ui.InjuryTag
import com.joescrepes.courtside.ui.LoadingPane
import com.joescrepes.courtside.ui.LocalGraph
import com.joescrepes.courtside.ui.LocalSnackbar
import com.joescrepes.courtside.ui.NbaLogo
import com.joescrepes.courtside.ui.StatColumn
import com.joescrepes.courtside.ui.Tag
import com.joescrepes.courtside.ui.label
import com.joescrepes.courtside.ui.pts
import com.joescrepes.courtside.ui.theme.Numeric
import com.joescrepes.courtside.ui.theme.Palette

private val POSITIONS = listOf("PG", "SG", "SF", "PF", "C")

@Composable
fun PlayersScreen() {
    val graph = LocalGraph.current
    val vm: PlayersViewModel = viewModel { PlayersViewModel(graph.api) }
    val ui by vm.ui.collectAsStateWithLifecycle()
    val snackbar = LocalSnackbar.current

    LaunchedEffect(ui.message) {
        ui.message?.let { snackbar.showSnackbar(it); vm.messageShown() }
    }

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        Text("Players", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.padding(start = 20.dp, top = 16.dp, bottom = 12.dp))
        SearchField(ui.filters.query, vm::setQuery)
        FilterRow(ui, vm)
        Box(Modifier.weight(1f)) {
            when {
                ui.error != null && ui.players.isEmpty() -> ErrorPane(ui.error!!, onRetry = { vm.retry() })
                ui.loading && ui.players.isEmpty() -> LoadingPane()
                else -> LazyColumn(
                    contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(ui.players, key = { it.id }) { p -> PlayerRow(p, ui.myTeamId, onClick = { vm.open(p) }) }
                    if (ui.players.isEmpty()) {
                        item {
                            Text("No players match.", color = Palette.TextDim, modifier = Modifier.fillMaxWidth().padding(32.dp))
                        }
                    }
                }
            }
            if (ui.loading && ui.players.isNotEmpty()) {
                CircularProgressIndicator(
                    color = Palette.Hardwood, strokeWidth = 2.dp,
                    modifier = Modifier.align(Alignment.TopCenter).padding(top = 8.dp).size(20.dp),
                )
            }
        }
    }

    ui.sheet?.let { sheet ->
        if (sheet.preview == null) {
            AddPicker(sheet, ui.myRoster, vm)
        } else {
            ConfirmSheet(
                title = if (sheet.waiver) "Waiver claim" else "Add player",
                summary = sheet.preview.summary,
                busy = sheet.busy,
                error = sheet.error,
                note = sheet.note,
                confirmLabel = if (sheet.waiver) "Submit claim" else "Confirm add",
                onConfirm = vm::confirm,
                onDismiss = vm::dismiss,
            )
        }
    }
}

@Composable
private fun SearchField(query: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = query,
        onValueChange = onChange,
        placeholder = { Text("Search any player") },
        leadingIcon = { Icon(Icons.Rounded.Search, null, tint = Palette.TextDim) },
        trailingIcon = {
            if (query.isNotEmpty()) IconButton(onClick = { onChange("") }) { Icon(Icons.Rounded.Close, "Clear", tint = Palette.TextDim) }
        },
        singleLine = true,
        shape = RoundedCornerShape(16.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Palette.Hardwood,
            unfocusedBorderColor = Palette.Line,
            focusedContainerColor = Palette.Panel,
            unfocusedContainerColor = Palette.Panel,
            cursorColor = Palette.Hardwood,
        ),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
    )
}

@Composable
private fun FilterRow(ui: PlayersUi, vm: PlayersViewModel) {
    val chipColors = FilterChipDefaults.filterChipColors(
        containerColor = Palette.Panel,
        labelColor = Palette.TextDim,
        selectedContainerColor = Palette.Hardwood.copy(alpha = 0.16f),
        selectedLabelColor = Palette.Hardwood,
    )
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        FilterChip(
            selected = ui.filters.availableOnly,
            onClick = { vm.setAvailableOnly(!ui.filters.availableOnly) },
            label = { Text("Available") },
            colors = chipColors,
            shape = RoundedCornerShape(12.dp),
        )
        Box(Modifier.width(1.dp).height(32.dp).background(Palette.Line).align(Alignment.CenterVertically))
        FilterChip(
            selected = ui.filters.position == null, onClick = { vm.setPosition(null) },
            label = { Text("All") }, colors = chipColors, shape = RoundedCornerShape(12.dp),
        )
        POSITIONS.forEach { pos ->
            FilterChip(
                selected = ui.filters.position == pos,
                onClick = { vm.setPosition(if (ui.filters.position == pos) null else pos) },
                label = { Text(pos) }, colors = chipColors, shape = RoundedCornerShape(12.dp),
            )
        }
    }
}

@Composable
private fun PlayerRow(p: Player, myTeamId: Int?, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(Palette.Panel)
            .border(1.dp, Palette.Line, RoundedCornerShape(18.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Headshot(p.id, p.name, size = 46.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(p.name, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                when {
                    p.status == "WAIVERS" -> Tag("WA", Palette.Sky)
                    p.onTeamId != null && p.onTeamId == myTeamId -> Tag("MINE", Palette.Hardwood)
                    p.status == "ONTEAM" -> Tag("TAKEN", Palette.TextFaint)
                }
                InjuryTag(p.injuryStatus)
            }
            Spacer(Modifier.height(2.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                NbaLogo(p.proTeam, size = 14.dp)
                Spacer(Modifier.width(5.dp))
                Text(
                    "${p.positions.joinToString("/")} · ${p.game?.label() ?: "No game today"}",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (p.game != null) Palette.TextDim else Palette.TextFaint,
                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Spacer(Modifier.width(8.dp))
        StatColumn(p.percentOwned?.let { "${it.toInt()}%" } ?: "–", "ROST", color = Palette.TextDim)
        Spacer(Modifier.width(14.dp))
        StatColumn(p.projected?.pts() ?: "–", "PROJ")
    }
}

/** First step of adding: player card plus who to drop. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddPicker(sheet: AddSheet, roster: List<Player>, vm: PlayersViewModel) {
    val p = sheet.player
    val available = p.status == "FREEAGENT" || p.status == "WAIVERS"
    ModalBottomSheet(
        onDismissRequest = vm::dismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = Palette.Panel,
        contentColor = Palette.Text,
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Headshot(p.id, p.name, size = 72.dp)
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text(p.name, style = MaterialTheme.typography.headlineSmall)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        NbaLogo(p.proTeam, size = 16.dp)
                        Spacer(Modifier.width(6.dp))
                        Text("${p.proTeam ?: ""} · ${p.positions.joinToString("/")}", style = MaterialTheme.typography.bodyMedium, color = Palette.TextDim)
                        Spacer(Modifier.width(6.dp))
                        InjuryTag(p.injuryStatus)
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Palette.PanelHigh).padding(vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceEvenly,
            ) {
                BigStat(p.projected?.pts() ?: "–", "PROJ AVG")
                BigStat(p.seasonAvg?.pts() ?: "–", "THIS SEASON")
                BigStat(p.lastSeasonAvg?.pts() ?: "–", "LAST SEASON")
                BigStat(p.percentOwned?.let { "${it.toInt()}%" } ?: "–", "ROSTERED")
            }
            p.game?.let {
                Text("Next: ${it.label()}", style = MaterialTheme.typography.bodySmall, color = Palette.TextDim, modifier = Modifier.padding(top = 10.dp))
            }

            if (!available) {
                Text(
                    "Already on a roster.", style = MaterialTheme.typography.bodyMedium, color = Palette.TextDim,
                    modifier = Modifier.padding(vertical = 20.dp),
                )
                return@Column
            }

            Spacer(Modifier.height(18.dp))
            Text("DROP", style = MaterialTheme.typography.labelSmall, color = Palette.TextDim)
            Spacer(Modifier.height(6.dp))
            Column(Modifier.heightIn(max = 300.dp).verticalScroll(rememberScrollState())) {
                DropOption(null, sheet.drop == null) { vm.chooseDrop(null) }
                roster.sortedBy { it.projected ?: 0.0 }.forEach { r ->
                    DropOption(r, sheet.drop?.id == r.id) { vm.chooseDrop(r) }
                }
            }
            if (sheet.error != null) {
                Text(sheet.error, color = Palette.Out, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 8.dp))
            }
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = vm::review,
                enabled = !sheet.busy,
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = RoundedCornerShape(16.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Palette.Hardwood, contentColor = Palette.Court),
            ) {
                if (sheet.busy) CircularProgressIndicator(color = Palette.Court, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
                else Text(if (sheet.waiver) "Review claim" else "Review add", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun BigStat(value: String, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = Numeric.copy(fontSize = MaterialTheme.typography.titleLarge.fontSize))
        Text(label, style = MaterialTheme.typography.labelSmall.copy(fontSize = MaterialTheme.typography.labelSmall.fontSize * 0.82f), color = Palette.TextFaint)
    }
}

@Composable
private fun DropOption(p: Player?, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(onClick = onClick).padding(vertical = 6.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = onClick, colors = RadioButtonDefaults.colors(selectedColor = Palette.Hardwood))
        if (p == null) {
            Text("Don't drop anyone", style = MaterialTheme.typography.bodyMedium, color = Palette.TextDim)
            return@Row
        }
        Headshot(p.id, p.name, size = 32.dp)
        Spacer(Modifier.width(10.dp))
        Text(p.name, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        InjuryTag(p.injuryStatus)
        Spacer(Modifier.width(8.dp))
        Text(p.projected?.pts() ?: "–", style = Numeric, color = Palette.TextDim)
    }
}
