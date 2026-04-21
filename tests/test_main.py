from src.main import main


def test_main(capsys):
    main()
    captured = capsys.readouterr()
    assert "Home budget scaffold ready" in captured.out
