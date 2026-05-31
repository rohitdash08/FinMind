import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const cardVariants = cva(
  "rounded-2xl border border-white/60 p-6 shadow-md transition-all duration-200 backdrop-blur-sm",
  {
    variants: {
      variant: {
        default: "bg-card/95 text-card-foreground",
        financial: "bg-gradient-card text-card-foreground hover:shadow-lg",
        premium: "bg-gradient-to-br from-card via-card to-primary-light/30 border-primary/25 shadow-primary hover:shadow-xl",
        success: "bg-success-light border-success/20 text-success",
        warning: "bg-warning-light border-warning/20 text-warning",
        destructive: "bg-destructive-light border-destructive/20 text-destructive",
      },
      size: {
        default: "p-6",
        sm: "p-4",
        lg: "p-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface FinancialCardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

const FinancialCard = React.forwardRef<HTMLDivElement, FinancialCardProps>(
  ({ className, variant, size, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(cardVariants({ variant, size, className }))}
      {...props}
    />
  )
)
FinancialCard.displayName = "FinancialCard"

const FinancialCardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5 pb-4", className)}
    {...props}
  />
))
FinancialCardHeader.displayName = "FinancialCardHeader"

const FinancialCardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn("font-semibold leading-none tracking-tight text-foreground", className)}
    {...props}
  />
))
FinancialCardTitle.displayName = "FinancialCardTitle"

const FinancialCardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
))
FinancialCardDescription.displayName = "FinancialCardDescription"

const FinancialCardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("", className)} {...props} />
))
FinancialCardContent.displayName = "FinancialCardContent"

const FinancialCardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center pt-4", className)}
    {...props}
  />
))
FinancialCardFooter.displayName = "FinancialCardFooter"

export {
  FinancialCard,
  FinancialCardHeader,
  FinancialCardTitle,
  FinancialCardDescription,
  FinancialCardContent,
  FinancialCardFooter,
}
