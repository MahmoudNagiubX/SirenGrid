plugins {
    id("com.android.application")
    // START: FlutterFire Configuration
    id("com.google.gms.google-services")
    // END: FlutterFire Configuration
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "eg.sirengrid.sirengrid_citizen"
    // flutter_secure_storage 11.x requires compileSdk 37 (installed:
    // platforms/android-37.0). AGP 9.1.0 warns but compiles fine; the warning
    // is suppressed in gradle.properties.
    compileSdk = maxOf(flutter.compileSdkVersion, 37)
    // Pinned to a locally-installed NDK so the build never triggers the
    // sdkmanager NDK auto-provision (which crashes under JDK 25 on this host).
    ndkVersion = "28.2.13676358"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "eg.sirengrid.sirengrid_citizen"
        // Firebase Messaging + geolocator floor; also covers Android 13 POST_NOTIFICATIONS.
        minSdk = maxOf(flutter.minSdkVersion, 23)
        targetSdk = flutter.targetSdkVersion
        multiDexEnabled = true
        // Demo target is the arm64 device (SM-A546E). Restricting ABIs keeps the
        // transitive `jni` package's native build off x86_64, whose sysroot in
        // the locally-installed NDK is incomplete on this host. A release build
        // for the Play Store would re-add arm64-v8a + armeabi-v7a (+ x86_64).
        ndk {
            abiFilters.clear()
            abiFilters.add("arm64-v8a")
        }
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
