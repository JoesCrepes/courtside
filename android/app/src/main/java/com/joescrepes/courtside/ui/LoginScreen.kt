package com.joescrepes.courtside.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.joescrepes.courtside.R
import com.joescrepes.courtside.ui.theme.Palette
import kotlinx.coroutines.launch

@Composable
fun LoginScreen() {
    val auth = LocalGraph.current.auth
    val scope = rememberCoroutineScope()
    var email by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun submit() {
        if (busy || email.isBlank() || password.isEmpty()) return
        busy = true
        error = null
        scope.launch {
            attempt { auth.signIn(email, password) }.onFailure { error = it.friendly() }
            busy = false
        }
    }

    val fieldColors = OutlinedTextFieldDefaults.colors(
        focusedBorderColor = Palette.Hardwood,
        unfocusedBorderColor = Palette.Line,
        focusedContainerColor = Palette.Panel,
        unfocusedContainerColor = Palette.Panel,
        cursorColor = Palette.Hardwood,
        focusedLabelColor = Palette.Hardwood,
    )

    Column(
        Modifier
            .fillMaxSize()
            .background(Palette.Court)
            .background(
                Brush.radialGradient(
                    listOf(Palette.Hardwood.copy(alpha = 0.22f), Palette.Court.copy(alpha = 0f)),
                    center = Offset(540f, 260f),
                    radius = 900f,
                )
            )
            .systemBarsPadding()
            .imePadding()
            .padding(horizontal = 28.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Image(
            painterResource(R.drawable.ic_launcher_foreground), contentDescription = null,
            modifier = Modifier.size(132.dp).align(Alignment.CenterHorizontally),
        )
        Text(
            "courtside",
            style = MaterialTheme.typography.displayMedium,
            modifier = Modifier.align(Alignment.CenterHorizontally),
        )
        Text(
            "Your league. No ads.",
            style = MaterialTheme.typography.bodyLarge,
            color = Palette.TextDim,
            modifier = Modifier.align(Alignment.CenterHorizontally),
        )
        Spacer(Modifier.height(40.dp))
        OutlinedTextField(
            value = email, onValueChange = { email = it },
            label = { Text("Email") }, singleLine = true, colors = fieldColors,
            shape = RoundedCornerShape(16.dp),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = password, onValueChange = { password = it },
            label = { Text("Password") }, singleLine = true, colors = fieldColors,
            shape = RoundedCornerShape(16.dp),
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Go),
            keyboardActions = KeyboardActions(onGo = { submit() }),
            modifier = Modifier.fillMaxWidth(),
        )
        if (error != null) {
            Text(error!!, color = Palette.Out, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 10.dp))
        }
        Spacer(Modifier.height(20.dp))
        Button(
            onClick = ::submit,
            enabled = !busy,
            modifier = Modifier.fillMaxWidth().height(56.dp),
            shape = RoundedCornerShape(18.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Palette.Hardwood, contentColor = Palette.Court),
        ) {
            if (busy) CircularProgressIndicator(color = Palette.Court, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
            else Text("Sign in", fontWeight = FontWeight.Bold)
        }
    }
}
