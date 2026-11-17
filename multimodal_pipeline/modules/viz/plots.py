import matplotlib.pyplot as plt

def correlation_heatmap(corr, title="Correlation Matrix"):
    plt.figure(figsize=(6, 5))
    plt.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
    plt.colorbar(label="Pearson r")
    labels = corr.columns
    plt.xticks(range(len(labels)), labels, rotation=45, ha="right")
    plt.yticks(range(len(labels)), labels)
    for i in range(len(labels)):
        for j in range(len(labels)):
            plt.text(j, i, f"{corr.iloc[i, j]:.2f}",
                     ha="center", va="center", color="black", fontsize=8)
    plt.title(title)
    plt.tight_layout()
    plt.show()
