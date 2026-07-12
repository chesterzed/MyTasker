./scripts/install.sh
launchctl list | grep com.mytasker.bot      # виден PID
tail -f logs/bot.err.log                      # "AimTracker bot started", без SSL-краша
pmset -g assertions | grep Prevent            # caffeinate держит ассерт против сна
./scripts/restart.sh                          # перезапуск (после git pull / правок)
./scripts/uninstall.sh                        # служба и plist исчезли