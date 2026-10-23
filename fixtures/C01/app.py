from datetime import date

def next_anniversary(today):
    try:
        return today.replace(year=today.year + 1)
    except ValueError:  # Feb 29 -> Feb 28
        return today.replace(year=today.year + 1, day=28)

if __name__ == "__main__":
    t = date.today()
    print("today", t, "-> next", next_anniversary(t))
