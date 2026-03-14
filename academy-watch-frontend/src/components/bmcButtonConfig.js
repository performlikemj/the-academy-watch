export const BMC_SCRIPT_SRC = 'https://cdnjs.buymeacoffee.com/1.0.0/button.prod.min.js'

export const BUTTON_DATASET = {
  text: 'Buy me a coffee',
  slug: 'TheAcademyWatch',
  color: '#100f0f',
  emoji: '',
  font: 'Cookie',
  fontColor: '#ffffff',
  outlineColor: '#ffffff',
  coffeeColor: '#FFDD00',
}

export function createBuyMeCoffeeScriptConfig() {
  return {
    type: 'text/javascript',
    src: BMC_SCRIPT_SRC,
    dataset: {
      name: 'bmc-button',
      slug: BUTTON_DATASET.slug,
      color: BUTTON_DATASET.color,
      emoji: BUTTON_DATASET.emoji,
      font: BUTTON_DATASET.font,
      text: BUTTON_DATASET.text,
      outlineColor: BUTTON_DATASET.outlineColor,
      fontColor: BUTTON_DATASET.fontColor,
      coffeeColor: BUTTON_DATASET.coffeeColor,
    },
  }
}
