//! The core against tests/golden/: behaviour recorded from the first version of the app,
//! kept so these rules can't drift by accident.

use serde_json::{Value, json};
use vimniscient::core::{answer, diagnose, keys, mnemonics, srs};

fn golden(name: &str) -> Value {
    let path = format!("{}/tests/golden/{name}", env!("CARGO_MANIFEST_DIR"));
    serde_json::from_str(&std::fs::read_to_string(path).expect("a golden file")).expect("JSON")
}

fn strings(value: &Value) -> Vec<String> {
    value.as_array().expect("a list").iter().map(|v| v.as_str().expect("a string").to_string()).collect()
}

#[test]
fn answers_check_the_same() {
    for case in golden("answers.json").as_array().unwrap() {
        let typed = case["typed"].as_str().unwrap();
        let expected = strings(&case["expected"]);
        let got = answer::is_correct(typed, &expected, case["style"].as_str().unwrap(), case["case_sensitive"].as_bool().unwrap());
        assert_eq!(got, case["correct"].as_bool().unwrap(), "{typed:?} against {expected:?}");
    }
}

#[test]
fn keys_count_normalise_and_explain_the_same() {
    let wanted = golden("keys.json");
    for (solution, want) in wanted.as_object().unwrap() {
        assert_eq!(keys::count_keys(solution), want["count"].as_u64().unwrap() as usize, "count of {solution}");
        assert_eq!(answer::norm_keys(solution, true), want["norm"].as_str().unwrap(), "norm of {solution}");
        assert_eq!(mnemonics::hooks(solution), strings(&want["hooks"]), "hooks of {solution}");
    }
}

#[test]
fn scheduling_steps_the_same() {
    let wanted = golden("srs.json");
    let day = chrono::NaiveDate::from_ymd_opt(2026, 10, 1).unwrap();
    for trail in wanted[0].as_array().unwrap() {
        let mut item = srs::Item::new("x", "card");
        for step in trail.as_array().unwrap() {
            srs::review(&mut item, step["grade"].as_u64().unwrap() as u8, day);
            assert!((item.interval - step["interval"].as_f64().unwrap()).abs() < 1e-9, "{step}");
            assert!((item.ease - step["ease"].as_f64().unwrap()).abs() < 1e-5, "{step}");
            assert_eq!(item.reps, step["reps"].as_i64().unwrap());
            assert_eq!(item.lapses, step["lapses"].as_i64().unwrap());
            assert_eq!(item.due.unwrap().to_string(), step["due"].as_str().unwrap());
        }
    }
    for case in wanted[1].as_array().unwrap() {
        let a = case["args"].as_array().unwrap();
        let got = srs::task_grade(a[0].as_str().unwrap(), a[1].as_u64().unwrap() as usize, a[2].as_u64().unwrap() as usize, a[3].as_u64().unwrap() as usize);
        assert_eq!(got.map(u64::from), case["grade"].as_u64(), "{case}");
    }
}

#[test]
fn strategy_feedback_says_the_same() {
    for case in golden("diagnose.json").as_array().unwrap() {
        let typed = case["keys"].as_str().unwrap();
        assert_eq!(json!(diagnose::normal_keys(typed)), case["normal"], "{typed}");
        assert_eq!(diagnose::diagnose(typed, keys::count_keys(typed), 2), case["says"].as_str().unwrap(), "{typed}");
    }
}
