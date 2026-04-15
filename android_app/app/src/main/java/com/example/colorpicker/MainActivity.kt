package com.example.colorpicker

import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.widget.Button
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val colorArea = findViewById<View>(R.id.colorArea)

        findViewById<Button>(R.id.btnRed).setOnClickListener {
            colorArea.setBackgroundColor(Color.rgb(255, 0, 0))
        }
        findViewById<Button>(R.id.btnGreen).setOnClickListener {
            colorArea.setBackgroundColor(Color.rgb(0, 255, 0))
        }
        findViewById<Button>(R.id.btnBlue).setOnClickListener {
            colorArea.setBackgroundColor(Color.rgb(0, 0, 255))
        }
        findViewById<Button>(R.id.btnWhite).setOnClickListener {
            colorArea.setBackgroundColor(Color.rgb(255, 255, 255))
        }
        findViewById<Button>(R.id.btnPurple).setOnClickListener {
            colorArea.setBackgroundColor(Color.rgb(255, 0, 255))
        }
        findViewById<Button>(R.id.btnYellow).setOnClickListener {
            colorArea.setBackgroundColor(Color.rgb(255, 255, 0))
        }
    }
}
