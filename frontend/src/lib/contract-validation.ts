import Ajv2020, { type ValidateFunction } from 'ajv/dist/2020.js'

export const contractValidator = new Ajv2020({ allErrors: true })

export const parseContract = <T>(validate: ValidateFunction<T>, value: unknown, message: string): T => {
  if (!validate(value)) throw new Error(message, { cause: validate.errors })
  return value
}
