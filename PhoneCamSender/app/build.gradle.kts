import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
}

val versionProperties = Properties().apply {
    rootProject.file("../version.properties").inputStream().use { load(it) }
}
val camflowVersion = versionProperties.getProperty("camflow.version")
    ?: error("camflow.version is missing from version.properties")
val camflowVersionCode = versionProperties.getProperty("camflow.versionCode")?.toInt()
    ?: error("camflow.versionCode is missing from version.properties")

android {
    namespace = "com.example.phonecamsender"
    compileSdk {
        version = release(36)
    }

    defaultConfig {
        applicationId = "com.example.phonecamsender"
        minSdk = 26
        targetSdk = 36
        versionCode = camflowVersionCode
        versionName = camflowVersion

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)
    implementation(libs.androidx.activity)
    implementation(libs.androidx.constraintlayout)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)

    val cameraxVersion = "1.3.4"

    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
