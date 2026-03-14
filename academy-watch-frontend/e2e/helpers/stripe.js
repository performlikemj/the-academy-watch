import { expect } from '@playwright/test'

async function fillIfVisible(locator, value) {
  if (await locator.count()) {
    const target = locator.first()
    if (await target.isVisible().catch(() => false)) {
      const enabled = await target.isEnabled().catch(() => false)
      if (!enabled) {
        return false
      }
      await target.fill(value)
      return true
    }
  }
  return false
}

async function clickIfVisible(locator) {
  if (await locator.count()) {
    const target = locator.first()
    if (await target.isVisible().catch(() => false)) {
      await target.click()
      return true
    }
  }
  return false
}

export async function completeStripeOnboarding(page, { email }) {
  await expect(page).toHaveURL(/connect\.stripe\.com/)

  for (let step = 0; step < 12; step += 1) {
    if (page.url().includes('/journalist/stripe-setup')) {
      break
    }

    await fillIfVisible(page.getByRole('textbox', { name: /Email/i }), email)
    await fillIfVisible(page.getByRole('textbox', { name: /Phone/i }), '+14155552671')

    await clickIfVisible(page.getByRole('button', { name: /Individual/i }))
    await clickIfVisible(page.getByRole('radio', { name: /Individual/i }))

    await fillIfVisible(page.getByRole('textbox', { name: /First name/i }), 'Test')
    await fillIfVisible(page.getByRole('textbox', { name: /Last name/i }), 'Reporter')

    await fillIfVisible(page.getByLabel(/Date of birth/i), '01 / 01 / 1990')
    await fillIfVisible(page.getByLabel(/Birth date/i), '01 / 01 / 1990')

    await fillIfVisible(page.getByRole('textbox', { name: /Address line 1/i }), '123 Main Street')
    await fillIfVisible(page.getByRole('textbox', { name: /City/i }), 'San Francisco')
    await fillIfVisible(page.getByRole('textbox', { name: /State/i }), 'CA')
    await fillIfVisible(page.getByRole('textbox', { name: /ZIP|Postal/i }), '94111')

    await fillIfVisible(page.getByRole('textbox', { name: /SSN|Tax ID|Social Security/i }), '0000')

    await fillIfVisible(page.getByRole('textbox', { name: /Routing number/i }), '110000000')
    await fillIfVisible(page.getByRole('textbox', { name: /Account number/i }), '000123456789')

    const continueButton = page.getByRole('button', { name: /Continue|Submit|Finish|Agree|Done|Save/i }).first()
    if (await continueButton.isVisible().catch(() => false)) {
      await continueButton.click()
      await page.waitForTimeout(1000)
      continue
    }

    const skipButton = page.getByRole('button', { name: /Skip/i }).first()
    if (await skipButton.isVisible().catch(() => false)) {
      await skipButton.click()
      await page.waitForTimeout(1000)
      continue
    }

    break
  }

  await expect(page).toHaveURL(/\/journalist\/stripe-setup/)
}

export async function completeStripeCheckout(page, { email }) {
  await expect(page).toHaveURL(/checkout\.stripe\.com/)

  await fillIfVisible(page.getByRole('textbox', { name: /Email/i }), email)
  await fillIfVisible(page.getByRole('textbox', { name: /Name/i }), 'E2E Subscriber')

  const frames = page.frameLocator('iframe[name^="__privateStripeFrame"]')
  const cardNumber = frames.getByPlaceholder('Card number')
  const cardExpiry = frames.getByPlaceholder('MM / YY')
  const cardCvc = frames.getByPlaceholder('CVC')
  const cardZip = frames.getByPlaceholder('ZIP')

  if (await cardNumber.count()) {
    await cardNumber.fill('4242 4242 4242 4242')
  }
  if (await cardExpiry.count()) {
    await cardExpiry.fill('12 / 30')
  }
  if (await cardCvc.count()) {
    await cardCvc.fill('123')
  }
  if (await cardZip.count()) {
    await cardZip.fill('94111')
  }

  const payButton = page.getByRole('button', { name: /Subscribe|Pay|Confirm/i }).first()
  await payButton.click()
}
