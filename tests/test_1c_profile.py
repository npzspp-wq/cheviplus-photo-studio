import app
import sapphire_profile_patch as profile


def test_confirmed_1c_profile_values():
    p = app.EXPORT_PROFILES[profile.ONE_C_PROFILE]
    assert p["width"] == 1280
    assert p["height"] == 960
    assert p["format"] == "JPG"
    assert p["target_kb"] == 0
    assert p["quality"] == 90


def test_visible_version_is_514():
    assert profile.APP_VERSION == "5.14"
    assert app.APP_VERSION == "5.14"
