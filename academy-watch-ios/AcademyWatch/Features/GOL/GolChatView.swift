import SwiftUI

struct GolChatView: View {
    @EnvironmentObject private var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var model: GolChatViewModel
    @State private var draft = ""
    @State private var showsSignIn = false
    @FocusState private var composerFocused: Bool

    var body: some View {
        NavigationStack {
            Group {
                if authManager.isAuthenticated {
                    conversation
                } else {
                    ContentUnavailableView {
                        Label("Ask GOL", systemImage: "bubble.left.and.bubble.right")
                .font(AcademyType.title2)
                .foregroundStyle(AcademyColors.text)
                    } description: {
                        Text("Sign in to ask about academy players and football pathways.")
                    } actions: {
                        Button("Sign in") { showsSignIn = true }
                            .buttonStyle(FloodlightPillStyle())
                            .tint(AcademyColors.primaryFill)
                            .foregroundStyle(AcademyColors.onPrimary)
                            .accessibilityIdentifier("gol-sign-in")
                    }
                }
            }
            .background(AcademyColors.background)
            .navigationTitle("GOL")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close", systemImage: "xmark") {
                        dismiss()
                    }
                    .accessibilityLabel("Close GOL")
                    .accessibilityIdentifier("gol-close")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("New chat", systemImage: "square.and.pencil") {
                        model.newChat()
                        draft = ""
                    }
                    .accessibilityLabel("New GOL chat")
                    .accessibilityIdentifier("gol-new-chat")
                    .disabled(!model.canStartNewChat)
                }
            }
        }
        .interactiveDismissDisabled(model.isStreaming)
        .onAppear { model.prepareForPresentation() }
        .sheet(isPresented: $showsSignIn) { SignInView(authManager: authManager) }
        .task(id: authManager.isAuthenticated) {
            if authManager.isAuthenticated { await model.loadSuggestions() }
        }
    }

    private var conversation: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        if model.messages.isEmpty { welcome }
                        ForEach(
                            model.messages.filter { !$0.content.isEmpty || !$0.cards.isEmpty || $0.cutShort }
                        ) { message in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(message.role == "user" ? "You" : "GOL")
                                    .font(AcademyType.caption.weight(.medium))
                                    .foregroundStyle(AcademyColors.accent)
                                if !message.content.isEmpty {
                                    Text(
                                        message.role == "assistant"
                                            ? GolMarkdown.render(message.content)
                                            : AttributedString(message.content)
                                    )
                                        .textSelection(.enabled)
                                        .accessibilityIdentifier(
                                            message.role == "assistant" ? "gol-answer" : "gol-question")
                                }
                                ForEach(Array(message.cards.enumerated()), id: \.offset) { _, card in
                                    GolDataCardView(card: card)
                                }
                                if message.cutShort {
                                    Label("Answer cut short", systemImage: "pause.circle")
                                        .font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
                                        .accessibilityIdentifier("gol-cut-short")
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(16)
                            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
                        }
                        if model.isStreaming {
                            HStack {
                                CleatLoader()
                                Text(model.isUsingTool ? "Looking up football data…" : "GOL is answering…")
                                    .font(AcademyType.footnote)
                            }
                            .accessibilityIdentifier("gol-streaming")
                        }
                        if let failure = model.failure {
                            Text(failure.message)
                                .font(AcademyType.callout)
                                .accessibilityIdentifier("gol-error")
                            if model.canRetry {
                                Button("Retry answer") { model.retry() }
                                    .buttonStyle(FloodlightPillStyle(variant: .outline))
                                    .accessibilityIdentifier("gol-retry")
                            }
                        }
                        Color.clear.frame(height: 1).id("gol-bottom")
                    }
                    .padding(18)
                }.background(AcademyColors.background)
                .accessibilityIdentifier("gol-messages")
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: model.messages.last?.content) { _, _ in
                    proxy.scrollTo("gol-bottom", anchor: .bottom)
                }
                .onChange(of: model.isStreaming) { _, _ in proxy.scrollTo("gol-bottom", anchor: .bottom) }
            }
            composer
        }
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 16) {
            Image(systemName: "bubble.left.and.bubble.right.fill")
                .font(AcademyType.largeTitle).foregroundStyle(AcademyColors.accent).accessibilityHidden(true)
            Text("Explore the game with GOL").font(AcademyType.title2)
            Text("Ask about academy players, their progress and their next steps.")
                .foregroundStyle(AcademyColors.secondaryText)
            ForEach(Array(model.suggestions.enumerated()), id: \.offset) { index, suggestion in
                Button {
                    submit(suggestion)
                } label: {
                    Text(verbatim: suggestion).multilineTextAlignment(.leading).padding(.vertical, 5)
                }
                .buttonStyle(FloodlightPillStyle(variant: .outline))
                .accessibilityIdentifier(index == 0 ? "gol-suggestion-0" : "gol-suggestion-\(index)")
                .disabled(!model.canSend)
            }
            Text("GOL can make mistakes. Check important details.").font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
        }
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let questionsLeft = model.questionsLeft {
                Text("Questions left: \(questionsLeft)")
                    .font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
                    .accessibilityIdentifier("gol-usage")
            }
            HStack(alignment: .bottom, spacing: 12) {
                TextField("Ask GOL…", text: $draft, axis: .vertical)
                    .lineLimit(1...5)
                    .focused($composerFocused)
                    .accessibilityLabel("Your question for GOL")
                    .accessibilityIdentifier("gol-composer")
                    .padding(12)
                    .background(AcademyColors.background, in: RoundedRectangle(cornerRadius: 10))
                    .disabled(!model.canSend)
                if model.isStreaming {
                    Button {
                        model.stop()
                    } label: {
                        Image(systemName: "stop.circle.fill").font(AcademyType.title).frame(minWidth: 44, minHeight: 44)
                    }
                    .accessibilityLabel("Stop GOL answer")
                    .accessibilityIdentifier("gol-stop")
                } else {
                    Button {
                        submit(draft)
                    } label: {
                        Image(systemName: "arrow.up.circle.fill").font(AcademyType.title).frame(
                            minWidth: 44, minHeight: 44)
                    }
                    .accessibilityLabel("Send question")
                    .accessibilityIdentifier("gol-send")
                    .disabled(!model.canSend || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .padding(16)
        .background(AcademyColors.surface)
    }

    private func submit(_ text: String) {
        composerFocused = false
        model.send(text)
        draft = ""
    }
}

private struct GolDataCardView: View {
    let card: GolJSON
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(verbatim: title).font(AcademyType.subheadline.bold())
            Text(verbatim: GolCardSummary(card: card).text).font(AcademyType.footnote)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(AcademyColors.background, in: RoundedRectangle(cornerRadius: 10))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("gol-data-card")
    }
    private var title: String {
        switch card["type"].string {
        case "analysis_result": return "Analysis"
        case "search_players", "get_player_stats", "get_team_loans": return "Players"
        case "get_player_journey": return "Player journey"
        case "get_cohort": return "Academy cohort"
        case "get_community_takes": return "Community views"
        default: return "Football data"
        }
    }
}

struct GolEntryButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: "bubble.left.and.bubble.right")
                Text("Ask GOL")
            }
        }
        .accessibilityLabel("Ask GOL")
        .accessibilityIdentifier("gol-landing-entry")
    }
}
