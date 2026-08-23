                          {player.contactable ? (
                            <button
                              type="button"
                              onClick={() => (auth?.token ? setIntroducePlayer(player) : openLoginModal())}
                              className="ml-0.5 inline-flex h-7 w-7 items-center justify-center rounded-full transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              aria-label={`Introduce yourself to ${player.player_name}`}
                              title="Introduce yourself"
                            >
                              <Send className="h-4 w-4 text-muted-foreground/60 hover:text-primary" />
                            </button>
                          ) : null}
