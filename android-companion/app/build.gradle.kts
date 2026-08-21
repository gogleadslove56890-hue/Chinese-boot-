plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android { namespace = "com.chineseboot.scanner"; compileSdk = 35
    buildFeatures { buildConfig = true }
    defaultConfig {
        applicationId = "com.chineseboot.scanner"
        minSdk = 26
        targetSdk = 35
        versionCode = 8
        versionName = "1.3.2"
        val backendUrl = providers.gradleProperty("scannerBackendUrl").orElse(
            providers.environmentVariable("SCANNER_BACKEND_URL")
        ).orElse("https://chinese-boot-1uvicorn-backend-app.onrender.com").get()
        require(backendUrl.startsWith("https://") && !backendUrl.contains(".github.dev", ignoreCase = true)) {
            "scannerBackendUrl must be a stable HTTPS production URL, never a GitHub Codespaces URL."
        }
        buildConfigField("String", "DEFAULT_BACKEND_URL", "\"https://chinese-boot-1uvicorn-backend-app.onrender.com\"")
    }
    buildTypes {
        getByName("release") {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_22
        targetCompatibility = JavaVersion.VERSION_22
    }
    kotlinOptions { jvmTarget = "22" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
}
